"""Unit tests for BoardColumnEventHandler."""

import logging
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

from codetoreum.application.event_handlers.board_event_handler import (
    BoardColumnEventHandler,
)
from codetoreum.application.agent_execution_recovery_service import (
    AgentExecutionRecoveryService,
)
from codetoreum.domain.board_workflow_template import (
    BoardWorkflowTemplate,
    ColumnTemplate,
    ColumnType,
)
from codetoreum.domain.events import (
    WorkItemColumnChangedEvent,
    AgentExecutionCompletedEvent,
)
from codetoreum.ports.output.board_service import (
    MovedByType,
    WorkItemPosition,
)
from codetoreum.ports.output.distributed_lock import (
    AcquireResult,
    AcquireStatus,
    ReleaseResult,
    ReleaseReason,
)
from codetoreum.infrastructure.event_bus import EventBus
from codetoreum.ports.exceptions import ResourceNotFoundError


@pytest.fixture
def mock_board_service():
    """Create mock board service."""
    service = AsyncMock()
    service.get_item_position = AsyncMock(
        return_value=WorkItemPosition(
            work_item_id="item-1",
            column_name="In Development",
            position=0,
        )
    )
    service.move_item_to_column = AsyncMock()
    service.get_items_in_column = AsyncMock(return_value=[])
    service.get_board = AsyncMock()
    return service


@pytest.fixture
def mock_distributed_lock():
    """Create mock distributed lock service."""
    from datetime import UTC
    service = AsyncMock()
    service.try_acquire = AsyncMock(
        return_value=AcquireResult(
            status=AcquireStatus.ACQUIRED,
            lock_key="proj-1:board-1",
            holder_id="item-1",
            acquired_at=datetime.now(UTC),
        )
    )
    service.release = AsyncMock(
        return_value=ReleaseResult(
            released=True,
            reason=None,
            lock_key="proj-1:board-1",
        )
    )
    return service


@pytest.fixture
def mock_pipeline_queue():
    """Create mock pipeline queue service."""
    service = AsyncMock()
    service.enqueue_item = AsyncMock()
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
    return EventBus()


@pytest.fixture
def mock_work_item_service():
    """Create mock work item service."""
    service = AsyncMock()
    service.get_work_item = AsyncMock()
    return service


@pytest.fixture
def mock_event_store():
    """Create mock event store."""
    store = AsyncMock()
    store.append = AsyncMock()
    return store


@pytest.fixture
def mock_run_registry():
    """Create mock run registry."""
    registry = AsyncMock()
    registry.set_active_run = AsyncMock()
    registry.get_active_run = AsyncMock(
        return_value=MagicMock(
            run_id="run-1",
            work_item_id="item-1",
            stage_name="In Development",
            project_id="proj-1",
            board_id="board-1",
            started_at=datetime.now(UTC).isoformat(),
        )
    )
    registry.clear_run = AsyncMock()
    return registry


@pytest.fixture
def mock_event_emitter():
    """Create mock event emitter."""
    return AsyncMock()


@pytest.fixture
def mock_recovery_service():
    """Create mock recovery service."""
    return AsyncMock()


@pytest.fixture
def handler(
    mock_board_service,
    mock_distributed_lock,
    mock_pipeline_queue,
    mock_workflow_config,
    mock_agent_executor,
    mock_event_bus,
    mock_work_item_service,
    mock_event_store,
    mock_run_registry,
    mock_event_emitter,
    mock_recovery_service,
):
    """Create handler with mocked dependencies."""
    return BoardColumnEventHandler(
        board_service=mock_board_service,
        workflow_config=mock_workflow_config,
        agent_executor=mock_agent_executor,
        event_bus=mock_event_bus,
        work_item_service=mock_work_item_service,
        distributed_lock=mock_distributed_lock,
        pipeline_queue=mock_pipeline_queue,
        event_store=mock_event_store,
        run_registry=mock_run_registry,
        event_emitter=mock_event_emitter,
        recovery_service=mock_recovery_service,
    )


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
                on_failure_column="Backlog",
            ),
            ColumnTemplate(
                name="Review",
                type=ColumnType.AUTOMATED,
                agent_id="agent-review",
                is_pipeline_trigger=False,
                is_exit_column=False,
                position=2,
                auto_progress_on_completion=True,
                on_failure_column="Backlog",
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


class TestGetEventTypes:
    """Tests for get_event_types method."""

    def test_returns_expected_event_types(self, handler):
        """Should return both column changed and agent completion event types."""
        event_types = handler.get_event_types()
        assert "WorkItemColumnChangedEvent" in event_types
        assert "AgentExecutionCompletedEvent" in event_types


class TestHandleColumnChangeWithPipelineTrigger:
    """Tests for pipeline trigger column handling."""

    @pytest.mark.asyncio
    async def test_acquires_lock_on_pipeline_trigger(
        self, handler, mock_distributed_lock, mock_pipeline_queue, sample_workflow_config
    ):
        """Should acquire lock when work item enters pipeline trigger column."""
        handler.workflow_config.get_board_workflow_template = AsyncMock(
            return_value=sample_workflow_config
        )

        event = WorkItemColumnChangedEvent(
            type="workitem.column_changed",
            timestamp=datetime.now(UTC).isoformat(),
            source="test",
            work_item_id="item-1",
            board_id="board-1",
            project_id="proj-1",
            from_column="Backlog",
            to_column="In Development",
            moved_by="human",
        )

        await handler.handle_column_change(event)

        # Verify lock acquisition was attempted
        mock_distributed_lock.try_acquire.assert_called_once()
        call_args = mock_distributed_lock.try_acquire.call_args
        assert call_args[1]["lock_key"] == "proj-1:board-1"
        assert call_args[1]["holder_id"] == "item-1"

    @pytest.mark.asyncio
    async def test_triggers_agent_on_lock_acquisition(
        self,
        handler,
        mock_distributed_lock,
        mock_agent_executor,
        sample_workflow_config,
    ):
        """Should trigger agent after successfully acquiring lock."""
        handler.workflow_config.get_board_workflow_template = AsyncMock(
            return_value=sample_workflow_config
        )

        event = WorkItemColumnChangedEvent(
            type="workitem.column_changed",
            timestamp=datetime.now(UTC).isoformat(),
            source="test",
            work_item_id="item-1",
            board_id="board-1",
            project_id="proj-1",
            from_column="Backlog",
            to_column="In Development",
            moved_by="human",
        )

        await handler.handle_column_change(event)

        # Verify agent was triggered
        mock_agent_executor.execute.assert_called_once()
        call_args = mock_agent_executor.execute.call_args
        assert call_args[1]["work_item_id"] == "item-1"
        assert call_args[1]["agent_id"] == "agent-dev"


class TestHandleExitColumn:
    """Tests for exit column handling."""

    @pytest.mark.asyncio
    async def test_releases_lock_on_exit_column(
        self,
        handler,
        mock_distributed_lock,
        sample_workflow_config,
    ):
        """Should release lock when work item enters exit column."""
        handler.workflow_config.get_board_workflow_template = AsyncMock(
            return_value=sample_workflow_config
        )

        event = WorkItemColumnChangedEvent(
            type="workitem.column_changed",
            timestamp=datetime.now(UTC).isoformat(),
            source="test",
            work_item_id="item-1",
            board_id="board-1",
            project_id="proj-1",
            from_column="Review",
            to_column="Done",
            moved_by="human",
        )

        await handler.handle_column_change(event)

        # Verify lock was released
        mock_distributed_lock.release.assert_called_once()
        call_args = mock_distributed_lock.release.call_args
        assert call_args[1]["lock_key"] == "proj-1:board-1"
        assert call_args[1]["holder_id"] == "item-1"

    @pytest.mark.asyncio
    async def test_completes_workflow_run_on_exit(
        self,
        handler,
        mock_run_registry,
        mock_event_store,
        sample_workflow_config,
    ):
        """Should complete workflow run when exiting."""
        handler.workflow_config.get_board_workflow_template = AsyncMock(
            return_value=sample_workflow_config
        )

        event = WorkItemColumnChangedEvent(
            type="workitem.column_changed",
            timestamp=datetime.now(UTC).isoformat(),
            source="test",
            work_item_id="item-1",
            board_id="board-1",
            project_id="proj-1",
            from_column="Review",
            to_column="Done",
            moved_by="human",
        )

        await handler.handle_column_change(event)

        # Verify event store was called for completion
        assert mock_event_store.append.called


class TestWorkflowRunLifecycle:
    """Tests for workflow run lifecycle management."""

    @pytest.mark.asyncio
    async def test_complete_workflow_run_clears_registry(
        self,
        handler,
        mock_run_registry,
        mock_event_store,
    ):
        """Should call clear_run on run registry when completing workflow."""
        await handler._complete_workflow_run(
            work_item_id="item-1",
            exit_column="Done",
        )

        # Verify clear_run was called (the fix for issue #904)
        mock_run_registry.clear_run.assert_called_once_with("item-1")

    @pytest.mark.asyncio
    async def test_fail_workflow_run_clears_registry(
        self,
        handler,
        mock_run_registry,
        mock_event_store,
    ):
        """Should call clear_run on run registry when failing workflow."""
        await handler._fail_workflow_run(
            work_item_id="item-1",
            reason="Agent execution failed",
        )

        # Verify clear_run was called
        mock_run_registry.clear_run.assert_called_once_with("item-1")

    @pytest.mark.asyncio
    async def test_complete_workflow_run_persists_event(
        self,
        handler,
        mock_run_registry,
        mock_event_store,
    ):
        """Should persist WorkflowCompletedEvent to event store."""
        await handler._complete_workflow_run(
            work_item_id="item-1",
            exit_column="Done",
        )

        # Verify event was persisted
        mock_event_store.append.assert_called_once()
        call_args = mock_event_store.append.call_args
        events = call_args[0][1]
        assert len(events) == 1
        assert events[0].type == "workflow.completed"
        assert events[0].work_item_id == "item-1"


class TestExistingRunCheckErrorHandling:
    """Tests for error handling in existing run check (the fix for silent errors)."""

    @pytest.mark.asyncio
    async def test_existing_run_check_error_logged_with_exc_info(
        self,
        handler,
        mock_run_registry,
        mock_event_store,
        sample_workflow_config,
        caplog,
    ):
        """Should log errors with exc_info when checking existing run and not proceed."""
        # Set up run registry to fail on the existing_run check
        test_error = Exception("Redis connection failed")
        mock_run_registry.get_active_run.side_effect = test_error

        handler.workflow_config.get_board_workflow_template = AsyncMock(
            return_value=sample_workflow_config
        )

        # Create an automated column event that bypasses pipeline trigger
        event = WorkItemColumnChangedEvent(
            type="workitem.column_changed",
            timestamp=datetime.now(UTC).isoformat(),
            source="test",
            work_item_id="item-1",
            board_id="board-1",
            project_id="proj-1",
            from_column="In Development",
            to_column="Review",
            moved_by="human",
        )

        with caplog.at_level(logging.ERROR):
            await handler.handle_column_change(event)

        # Verify error was logged at ERROR level with exc_info
        assert any(
            "Failed to check existing run for item-1" in record.message
            and record.levelname == "ERROR"
            for record in caplog.records
        )

        # Verify that no workflow was started (early return prevents _start_workflow_run)
        # The event_store.append should not be called for a new workflow
        mock_event_store.append.assert_not_called()

    @pytest.mark.asyncio
    async def test_existing_run_none_starts_new_workflow(
        self,
        handler,
        mock_run_registry,
        mock_event_store,
        sample_workflow_config,
    ):
        """Should start new workflow when no existing run exists."""
        # Set up: no existing run
        mock_run_registry.get_active_run.return_value = None

        handler.workflow_config.get_board_workflow_template = AsyncMock(
            return_value=sample_workflow_config
        )

        automated_column = sample_workflow_config.columns[2]  # Review column
        event = WorkItemColumnChangedEvent(
            type="workitem.column_changed",
            timestamp=datetime.now(UTC).isoformat(),
            source="test",
            work_item_id="item-1",
            board_id="board-1",
            project_id="proj-1",
            from_column="In Development",
            to_column="Review",
            moved_by="human",
        )

        await handler.handle_column_change(event)

        # Verify start_workflow_run was called
        assert mock_event_store.append.called
        call_args = mock_event_store.append.call_args
        events = call_args[0][1]
        assert any(e.type == "workflow.created" for e in events)


class TestAgentExecutionCompletion:
    """Tests for agent execution completion handling."""

    @pytest.mark.asyncio
    async def test_handle_agent_execution_completed_event(
        self,
        handler,
        sample_workflow_config,
    ):
        """Should handle AgentExecutionCompletedEvent and auto-progress."""
        handler.workflow_config.get_board_workflow_template = AsyncMock(
            return_value=sample_workflow_config
        )
        # Set up board service to return current position
        handler.board_service.get_item_position = AsyncMock(
            return_value=WorkItemPosition(
                work_item_id="item-1",
                column_name="Review",  # Current column
                position=0,
            )
        )
        handler.board_service.move_item_to_column = AsyncMock()
        handler.board_service.get_board = AsyncMock()

        event = AgentExecutionCompletedEvent(
            type="agent.execution_completed",
            timestamp=datetime.now(UTC).isoformat(),
            source="test",
            work_item_id="item-1",
            board_id="board-1",
            success=True,
        )

        await handler.handle(event)

        # Verify auto-progression occurred (should move from Review to Done)
        handler.board_service.move_item_to_column.assert_called()
        call_args = handler.board_service.move_item_to_column.call_args
        assert call_args[0][0] == "item-1"
        assert call_args[0][1] == "Done"

    @pytest.mark.asyncio
    async def test_failed_agent_routes_to_failure_column(
        self,
        handler,
        sample_workflow_config,
    ):
        """Should route failed items to on_failure_column."""
        handler.workflow_config.get_board_workflow_template = AsyncMock(
            return_value=sample_workflow_config
        )

        event = AgentExecutionCompletedEvent(
            type="agent.execution_completed",
            timestamp=datetime.now(UTC).isoformat(),
            source="test",
            work_item_id="item-1",
            board_id="board-1",
            success=False,
        )

        await handler.handle(event)

        # Verify that the item was moved to the failure column
        handler.board_service.move_item_to_column.assert_called_once()
        call_args = handler.board_service.move_item_to_column.call_args
        assert call_args[0][0] == "item-1"  # work_item_id
        assert call_args[0][1] == "Backlog"  # on_failure_column from fixture
        assert call_args[0][2] == MovedByType.ORCHESTRATOR


class TestErrorRecovery:
    """Tests for error recovery patterns."""

    @pytest.mark.asyncio
    async def test_agent_execution_failure_releases_lock(
        self,
        handler,
        mock_agent_executor,
        mock_distributed_lock,
        sample_workflow_config,
    ):
        """Should release lock when agent execution fails."""
        # Set up agent to fail
        test_error = Exception("Agent execution error")
        mock_agent_executor.execute.side_effect = test_error

        handler.workflow_config.get_board_workflow_template = AsyncMock(
            return_value=sample_workflow_config
        )

        await handler._trigger_agent(
            work_item_id="item-1",
            column_config=sample_workflow_config.columns[1],
            board_id="board-1",
        )

        # Verify lock was released on failure
        mock_distributed_lock.release.assert_called()

    @pytest.mark.asyncio
    async def test_lock_release_failure_emits_event(
        self,
        handler,
        mock_distributed_lock,
        mock_event_emitter,
        sample_workflow_config,
    ):
        """Should emit LockStuckEvent when lock release fails."""
        # Set up lock release to fail
        mock_distributed_lock.release.side_effect = Exception(
            "Lock service unavailable"
        )

        handler.workflow_config.get_board_workflow_template = AsyncMock(
            return_value=sample_workflow_config
        )
        handler.board_service.get_board = AsyncMock()

        event = WorkItemColumnChangedEvent(
            type="workitem.column_changed",
            timestamp=datetime.now(UTC).isoformat(),
            source="test",
            work_item_id="item-1",
            board_id="board-1",
            project_id="proj-1",
            from_column="Review",
            to_column="Done",
            moved_by="human",
        )

        await handler.handle_column_change(event)

        # Verify LockStuckEvent was emitted
        assert mock_event_emitter.emit.called


class TestRunRegistryStateManagement:
    """Tests for run registry state management (the fix for state leak)."""

    @pytest.mark.asyncio
    async def test_start_workflow_run_registers_run(
        self,
        handler,
        mock_run_registry,
        mock_event_store,
        sample_workflow_config,
    ):
        """Should register run in registry when starting workflow."""
        await handler._start_workflow_run(
            work_item_id="item-1",
            project_id="proj-1",
            board_id="board-1",
            column_config=sample_workflow_config.columns[1],
            workflow_config=sample_workflow_config,
        )

        # Verify run was registered
        mock_run_registry.set_active_run.assert_called_once()
        call_args = mock_run_registry.set_active_run.call_args
        assert call_args[1]["work_item_id"] == "item-1"
        assert call_args[1]["stage_name"] == "In Development"

    @pytest.mark.asyncio
    async def test_complete_workflow_run_clears_run_state(
        self,
        handler,
        mock_run_registry,
        mock_event_store,
    ):
        """Should clear run state from registry when completing workflow (fix for #904)."""
        await handler._complete_workflow_run(
            work_item_id="item-1",
            exit_column="Done",
        )

        # This is the critical fix: clear_run MUST be called
        mock_run_registry.clear_run.assert_called_once_with("item-1")

    @pytest.mark.asyncio
    async def test_completed_runs_do_not_accumulate(
        self,
        handler,
        mock_run_registry,
        mock_event_store,
    ):
        """Verify that completed workflow runs are cleared from registry."""
        # Simulate multiple completions
        for i in range(3):
            await handler._complete_workflow_run(
                work_item_id=f"item-{i}",
                exit_column="Done",
            )

        # Verify clear_run was called for each completion
        assert mock_run_registry.clear_run.call_count == 3
