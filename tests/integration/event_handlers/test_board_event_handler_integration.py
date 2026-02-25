"""Integration tests for BoardColumnEventHandler with mock adapters."""

from unittest.mock import AsyncMock

import pytest

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
from codetoreum.infrastructure.event_bus import EventBus
from codetoreum.ports.output.board_service import MovedByType, WorkItemPosition


@pytest.fixture
def event_bus():
    """Create event bus."""
    return EventBus()


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
def handler(
    event_bus,
    mock_board_service,
    mock_lock_service,
    mock_workflow_config,
    mock_agent_executor,
):
    """Create handler with mocked dependencies."""
    return BoardColumnEventHandler(
        board_service=mock_board_service,
        lock_service=mock_lock_service,
        workflow_config=mock_workflow_config,
        agent_executor=mock_agent_executor,
        event_bus=event_bus,
    )


@pytest.fixture
def sdlc_workflow():
    """SDLC workflow template for testing."""
    return BoardWorkflowTemplate(
        id="workflow-1",
        name="SDLC Workflow",
        pipeline_trigger_columns=("Development",),
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
                name="Development",
                type=ColumnType.AUTOMATED,
                agent_id="agent-dev",
                is_pipeline_trigger=True,
                is_exit_column=False,
                position=1,
                auto_progress_on_completion=False,
            ),
            ColumnTemplate(
                name="Code Review",
                type=ColumnType.AUTOMATED,
                agent_id="agent-review",
                is_pipeline_trigger=False,
                is_exit_column=False,
                position=2,
                auto_progress_on_completion=True,
            ),
            ColumnTemplate(
                name="Testing",
                type=ColumnType.AUTOMATED,
                agent_id="agent-test",
                is_pipeline_trigger=False,
                is_exit_column=False,
                position=3,
                auto_progress_on_completion=True,
            ),
            ColumnTemplate(
                name="Done",
                type=ColumnType.MANUAL,
                agent_id=None,
                is_pipeline_trigger=False,
                is_exit_column=True,
                position=4,
                auto_progress_on_completion=False,
            ),
        ),
    )


class TestEndToEndColumnChangeWorkflow:
    """Integration tests for complete column change workflows."""

    @pytest.mark.asyncio
    async def test_full_sdlc_workflow_with_pipeline_lock(
        self,
        handler,
        event_bus,
        mock_board_service,
        mock_lock_service,
        mock_workflow_config,
        mock_agent_executor,
        sdlc_workflow,
    ):
        """Test complete SDLC workflow from development through completion."""
        mock_workflow_config.get_board_workflow_template.return_value = sdlc_workflow
        event_bus.register_handler(handler)

        # Stage 1: Item moves to Development (trigger column)
        # Lock acquired, dev agent triggered
        mock_lock_service.try_acquire_lock.return_value = LockAcquisitionResult(
            status=LockStatus.ACQUIRED,
            work_item_id="item-1",
            queue_length=0,
        )

        dev_event = WorkItemColumnChanged(
            aggregate_id="item-1",
            payload={
                "work_item_id": "item-1",
                "board_id": "board-1",
                "project_id": "proj-1",
                "from_column": "Backlog",
                "to_column": "Development",
                "moved_by": "human",
            },
        )

        await event_bus.publish(dev_event)

        # Verify lock acquired and dev agent triggered
        mock_lock_service.try_acquire_lock.assert_called_once()
        mock_agent_executor.execute.assert_called_with(
            work_item_id="item-1", agent_id="agent-dev"
        )

        # Stage 2: Item moves to Code Review (automated, auto-progress enabled)
        mock_agent_executor.reset_mock()
        mock_board_service.get_item_position.return_value = WorkItemPosition(
            work_item_id="item-1",
            column_name="Code Review",
            position=0,
        )

        review_event = WorkItemColumnChanged(
            aggregate_id="item-1",
            payload={
                "work_item_id": "item-1",
                "board_id": "board-1",
                "project_id": "proj-1",
                "from_column": "Development",
                "to_column": "Code Review",
                "moved_by": "orchestrator",
            },
        )

        await event_bus.publish(review_event)

        # Verify review agent triggered
        mock_agent_executor.execute.assert_called_with(
            work_item_id="item-1", agent_id="agent-review"
        )

        # Stage 3: Item reaches Done (exit column)
        # Lock released, no more processing
        mock_agent_executor.reset_mock()
        mock_lock_service.release_lock.return_value = LockReleaseResult(
            released_work_item_id="item-1",
            next_work_item_id=None,  # No queue
            queue_length_after_release=0,
        )

        done_event = WorkItemColumnChanged(
            aggregate_id="item-1",
            payload={
                "work_item_id": "item-1",
                "board_id": "board-1",
                "project_id": "proj-1",
                "from_column": "Testing",
                "to_column": "Done",
                "moved_by": "orchestrator",
            },
        )

        await event_bus.publish(done_event)

        # Verify lock released
        mock_lock_service.release_lock.assert_called_once()

    @pytest.mark.asyncio
    async def test_lock_queuing_workflow(
        self,
        handler,
        event_bus,
        mock_board_service,
        mock_lock_service,
        mock_workflow_config,
        mock_agent_executor,
        sdlc_workflow,
    ):
        """Test workflow with lock queuing due to contention."""
        mock_workflow_config.get_board_workflow_template.return_value = sdlc_workflow
        event_bus.register_handler(handler)

        # Item 1 moves to Development, acquires lock
        mock_lock_service.try_acquire_lock.return_value = LockAcquisitionResult(
            status=LockStatus.ACQUIRED,
            work_item_id="item-1",
            queue_length=0,
        )

        event1 = WorkItemColumnChanged(
            aggregate_id="item-1",
            payload={
                "work_item_id": "item-1",
                "board_id": "board-1",
                "project_id": "proj-1",
                "from_column": "Backlog",
                "to_column": "Development",
                "moved_by": "human",
            },
        )

        await event_bus.publish(event1)
        assert mock_agent_executor.execute.call_count == 1

        # Item 2 moves to Development, gets queued
        mock_agent_executor.reset_mock()
        mock_lock_service.try_acquire_lock.return_value = LockAcquisitionResult(
            status=LockStatus.QUEUED,
            work_item_id="item-2",
            queue_position=1,
            queue_length=2,
        )
        mock_board_service.get_item_position.return_value = WorkItemPosition(
            work_item_id="item-2",
            column_name="Development",
            position=1,
        )

        event2 = WorkItemColumnChanged(
            aggregate_id="item-2",
            payload={
                "work_item_id": "item-2",
                "board_id": "board-1",
                "project_id": "proj-1",
                "from_column": "Backlog",
                "to_column": "Development",
                "moved_by": "human",
            },
        )

        await event_bus.publish(event2)

        # Agent should not be triggered for queued item
        mock_agent_executor.execute.assert_not_called()

        # Item 1 reaches exit column, releases lock to item 2
        mock_agent_executor.reset_mock()
        mock_lock_service.release_lock.return_value = LockReleaseResult(
            released_work_item_id="item-1",
            next_work_item_id="item-2",
            queue_length_after_release=1,
        )
        mock_board_service.get_item_position.return_value = WorkItemPosition(
            work_item_id="item-2",
            column_name="Development",
            position=1,
        )

        exit_event = WorkItemColumnChanged(
            aggregate_id="item-1",
            payload={
                "work_item_id": "item-1",
                "board_id": "board-1",
                "project_id": "proj-1",
                "from_column": "Testing",
                "to_column": "Done",
                "moved_by": "orchestrator",
            },
        )

        await event_bus.publish(exit_event)

        # Now item 2's agent should be triggered
        mock_agent_executor.execute.assert_called_with(
            work_item_id="item-2", agent_id="agent-dev"
        )

    @pytest.mark.asyncio
    async def test_auto_progression_chain(
        self,
        handler,
        event_bus,
        mock_board_service,
        mock_workflow_config,
        sdlc_workflow,
    ):
        """Test auto-progression through multiple columns."""
        mock_workflow_config.get_board_workflow_template.return_value = sdlc_workflow
        event_bus.register_handler(handler)

        # Agent completes review phase successfully
        mock_board_service.get_item_position.return_value = WorkItemPosition(
            work_item_id="item-1",
            column_name="Code Review",
            position=0,
        )

        await handler.handle_agent_completion(
            work_item_id="item-1",
            board_id="board-1",
            success=True,
        )

        # Should auto-progress to Testing
        mock_board_service.move_item_to_column.assert_called_with(
            "item-1", "Testing", MovedByType.ORCHESTRATOR
        )

        # Simulate item now in Testing
        mock_board_service.get_item_position.return_value = WorkItemPosition(
            work_item_id="item-1",
            column_name="Testing",
            position=0,
        )

        await handler.handle_agent_completion(
            work_item_id="item-1",
            board_id="board-1",
            success=True,
        )

        # Should auto-progress to Done
        calls = mock_board_service.move_item_to_column.call_args_list
        assert calls[-1][0] == ("item-1", "Done", MovedByType.ORCHESTRATOR)


class TestErrorRecovery:
    """Tests for error handling and recovery."""

    @pytest.mark.asyncio
    async def test_handler_continues_after_exception(
        self,
        handler,
        event_bus,
        mock_agent_executor,
        mock_workflow_config,
        sdlc_workflow,
    ):
        """Handler should continue processing after exception in one event."""
        mock_workflow_config.get_board_workflow_template.return_value = sdlc_workflow
        mock_agent_executor.execute.side_effect = RuntimeError("Agent error")

        # Register handler
        event_bus.register_handler(handler)

        # First event causes exception
        event1 = WorkItemColumnChanged(
            aggregate_id="item-1",
            payload={
                "work_item_id": "item-1",
                "board_id": "board-1",
                "project_id": "proj-1",
                "from_column": "Backlog",
                "to_column": "Development",
                "moved_by": "human",
            },
        )

        # Should not raise
        await event_bus.publish(event1)

        # Second event should still be processed
        mock_agent_executor.reset_mock()
        mock_agent_executor.execute.side_effect = None

        event2 = WorkItemColumnChanged(
            aggregate_id="item-2",
            payload={
                "work_item_id": "item-2",
                "board_id": "board-1",
                "project_id": "proj-1",
                "from_column": "Development",
                "to_column": "Code Review",
                "moved_by": "human",
            },
        )

        # Reset position for second item
        mock_agent_executor.execute.return_value = None

        await event_bus.publish(event2)

        # Second event should still execute agent
        mock_agent_executor.execute.assert_called()


class TestMultipleBoardsAndProjects:
    """Tests for handling multiple boards and projects."""

    @pytest.mark.asyncio
    async def test_different_workflows_per_board(
        self,
        handler,
        event_bus,
        mock_board_service,
        mock_lock_service,
        mock_workflow_config,
        mock_agent_executor,
        sdlc_workflow,
    ):
        """Should handle different workflow configurations per board."""
        # Board 1 uses SDLC workflow
        # Board 2 uses different workflow
        simple_workflow = BoardWorkflowTemplate(
            id="workflow-2",
            name="Simple Workflow",
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
                ColumnTemplate(
                    name="Done",
                    type=ColumnType.MANUAL,
                    agent_id=None,
                    is_pipeline_trigger=False,
                    is_exit_column=False,
                    position=1,
                    auto_progress_on_completion=False,
                ),
            ),
        )

        # Configure board-specific workflows
        def get_workflow(board_id):
            if board_id == "board-1":
                return sdlc_workflow
            if board_id == "board-2":
                return simple_workflow
            return None

        mock_workflow_config.get_board_workflow_template.side_effect = get_workflow
        event_bus.register_handler(handler)

        # Event for board 1 (SDLC workflow)
        mock_lock_service.try_acquire_lock.return_value = LockAcquisitionResult(
            status=LockStatus.ACQUIRED,
            work_item_id="item-1",
            queue_length=0,
        )

        event1 = WorkItemColumnChanged(
            aggregate_id="item-1",
            payload={
                "work_item_id": "item-1",
                "board_id": "board-1",
                "project_id": "proj-1",
                "from_column": "Backlog",
                "to_column": "Development",
                "moved_by": "human",
            },
        )

        await event_bus.publish(event1)
        assert mock_agent_executor.execute.call_count == 1

        # Event for board 2 (simple workflow, no agents)
        mock_agent_executor.reset_mock()
        event2 = WorkItemColumnChanged(
            aggregate_id="item-2",
            payload={
                "work_item_id": "item-2",
                "board_id": "board-2",
                "project_id": "proj-1",
                "from_column": "Todo",
                "to_column": "Done",
                "moved_by": "human",
            },
        )

        await event_bus.publish(event2)

        # No agent should be triggered for simple workflow
        mock_agent_executor.execute.assert_not_called()
