"""Unit tests for AgentExecutionRecoveryService.

Tests recovery mechanisms for:
1. Completion callback failures (auto-progression stuck) via DeadLetterQueue
2. Agent execution failures (lock release failures)
"""

from unittest.mock import AsyncMock, MagicMock

import pytest

from codetoreum.adapters.secondary.failed_event_store_adapter import (
    DeadLetterQueueFailedEventStoreAdapter,
)
from codetoreum.application.agent_execution_recovery_service import (
    AgentExecutionRecoveryService,
)
from codetoreum.infrastructure.dead_letter_queue import DeadLetterQueue
from codetoreum.ports.output.active_workflow_run_registry import ActiveRunInfo


class TestAgentExecutionRecoveryService:
    """Test recovery service behavior."""

    @pytest.fixture
    def recovery_service(self):
        """Create recovery service with mocked dependencies."""
        board_service = AsyncMock()
        event_store = AsyncMock()
        run_registry = AsyncMock()

        # Mock board service to return position
        position = MagicMock()
        position.column_name = "In Development"
        position.position = 1
        board_service.get_item_position.return_value = position

        # Create the required failed_event_store adapter
        dead_letter_queue = DeadLetterQueue()
        failed_event_store = DeadLetterQueueFailedEventStoreAdapter(dead_letter_queue)

        service = AgentExecutionRecoveryService(
            board_service=board_service,
            event_store=event_store,
            run_registry=run_registry,
            failed_event_store=failed_event_store,
        )
        service._board_service = board_service
        service._event_store = event_store
        service._run_registry = run_registry
        return service

    @pytest.mark.asyncio
    async def test_completion_callback_failure_queues_for_recovery(self, recovery_service):
        """When completion callback fails, work item is queued in DeadLetterQueue."""
        # Arrange
        work_item_id = "wi-1"
        board_id = "board-1"
        error = RuntimeError("Auto-progression failed")

        recovery_service._run_registry.get_active_run.return_value = None

        # Act
        await recovery_service.handle_completion_callback_failure(
            work_item_id=work_item_id,
            board_id=board_id,
            success=True,
            error=error,
        )

        # Assert: Work item in dead letter queue (via failed event store)
        stuck_items = recovery_service.get_stuck_work_items()
        assert work_item_id in stuck_items

        # Verify the event data contains expected fields
        stats = recovery_service.get_failed_event_store_stats()
        assert stats.total_failed_events == 1

    @pytest.mark.asyncio
    async def test_completion_callback_failure_fails_workflow_run(self, recovery_service):
        """When completion callback fails, workflow run is marked as failed."""
        # Arrange
        work_item_id = "wi-1"
        board_id = "board-1"
        run_id = "run-1"
        stage_name = "coding"
        error = RuntimeError("Auto-progression failed")

        run_info = ActiveRunInfo(
            work_item_id=work_item_id,
            run_id=run_id,
            stage_name=stage_name,
            project_id="proj-1",
        )
        recovery_service._run_registry.get_active_run.return_value = run_info

        # Act
        await recovery_service.handle_completion_callback_failure(
            work_item_id=work_item_id,
            board_id=board_id,
            success=True,
            error=error,
        )

        # Assert: WorkflowFailed event appended
        assert recovery_service._event_store.append.called
        call_args = recovery_service._event_store.append.call_args
        assert call_args[0][0] == run_id
        events = call_args[0][1]
        assert len(events) == 1
        assert events[0].work_item_id == work_item_id

    @pytest.mark.asyncio
    async def test_agent_execution_failure_fails_workflow_run(self, recovery_service):
        """When agent execution fails, workflow run is marked as failed."""
        # Arrange
        work_item_id = "wi-1"
        board_id = "board-1"
        run_id = "run-1"
        stage_name = "coding"
        error = RuntimeError("Agent execution failed")

        run_info = ActiveRunInfo(
            work_item_id=work_item_id,
            run_id=run_id,
            stage_name=stage_name,
            project_id="proj-1",
        )
        recovery_service._run_registry.get_active_run.return_value = run_info

        # Act
        await recovery_service.handle_agent_execution_failure(
            work_item_id=work_item_id,
            board_id=board_id,
            error=error,
        )

        # Assert: WorkflowFailed event appended
        assert recovery_service._event_store.append.called
        call_args = recovery_service._event_store.append.call_args
        assert call_args[0][0] == run_id
        events = call_args[0][1]
        assert len(events) == 1
        assert events[0].work_item_id == work_item_id

    @pytest.mark.asyncio
    async def test_get_stuck_work_items_returns_dlq_items(self, recovery_service):
        """Get stuck work items returns all work items in dead letter queue."""
        # Arrange
        await recovery_service.handle_completion_callback_failure(
            work_item_id="wi-1",
            board_id="board-1",
            success=True,
            error=RuntimeError("Failed 1"),
        )
        await recovery_service.handle_completion_callback_failure(
            work_item_id="wi-2",
            board_id="board-1",
            success=True,
            error=RuntimeError("Failed 2"),
        )
        recovery_service._run_registry.get_active_run.return_value = None

        # Act
        stuck_items = recovery_service.get_stuck_work_items()

        # Assert
        assert "wi-1" in stuck_items
        assert "wi-2" in stuck_items
        assert len(stuck_items) == 2

    @pytest.mark.asyncio
    async def test_board_service_none_does_not_crash(self, recovery_service):
        """When board_service is None, should not crash but use 'UNKNOWN' column."""
        # Arrange
        recovery_service._board_service = None
        work_item_id = "wi-1"
        board_id = "board-1"
        error = RuntimeError("Auto-progression failed")

        recovery_service._run_registry.get_active_run.return_value = None

        # Act - should not raise AttributeError
        await recovery_service.handle_completion_callback_failure(
            work_item_id=work_item_id,
            board_id=board_id,
            success=True,
            error=error,
        )

        # Assert: Work item should still be queued with 'UNKNOWN' column
        stuck_items = recovery_service.get_stuck_work_items()
        assert work_item_id in stuck_items

    @pytest.mark.asyncio
    async def test_missing_run_registry_logs_warning(self, recovery_service, caplog):
        """When run_registry is None, should log warning instead of silently no-op."""
        # Arrange
        recovery_service._run_registry = None
        work_item_id = "wi-1"
        board_id = "board-1"
        error = RuntimeError("Completion callback failed")

        # Act
        await recovery_service.handle_completion_callback_failure(
            work_item_id=work_item_id,
            board_id=board_id,
            success=True,
            error=error,
        )

        # Assert: Warning logged about missing run_registry
        assert any(
            "run_registry dependency not wired" in record.message and record.levelname == "WARNING"
            for record in caplog.records
        )
        assert any(record.error_id == "ERR_AGENT_EXECUTION_MISSING_RUN_REGISTRY" for record in caplog.records)

    @pytest.mark.asyncio
    async def test_missing_event_store_logs_warning(self, recovery_service, caplog):
        """When event_store is None, should log warning instead of silently no-op."""
        # Arrange
        recovery_service._event_store = None
        work_item_id = "wi-1"
        board_id = "board-1"
        run_id = "run-1"
        stage_name = "coding"
        error = RuntimeError("Completion callback failed")

        run_info = ActiveRunInfo(
            work_item_id=work_item_id,
            run_id=run_id,
            stage_name=stage_name,
            project_id="proj-1",
        )
        recovery_service._run_registry.get_active_run.return_value = run_info

        # Act
        await recovery_service.handle_completion_callback_failure(
            work_item_id=work_item_id,
            board_id=board_id,
            success=True,
            error=error,
        )

        # Assert: Warning logged about missing event_store
        assert any(
            "event_store dependency not wired" in record.message and record.levelname == "WARNING"
            for record in caplog.records
        )
        assert any(record.error_id == "ERR_AGENT_EXECUTION_MISSING_EVENT_STORE" for record in caplog.records)

    @pytest.mark.asyncio
    async def test_missing_event_store_on_agent_execution_failure_logs_warning(self, recovery_service, caplog):
        """When event_store is None during agent execution failure, should log warning."""
        # Arrange
        recovery_service._event_store = None
        work_item_id = "wi-1"
        board_id = "board-1"
        run_id = "run-1"
        stage_name = "coding"
        error = RuntimeError("Agent execution failed")

        run_info = ActiveRunInfo(
            work_item_id=work_item_id,
            run_id=run_id,
            stage_name=stage_name,
            project_id="proj-1",
        )
        recovery_service._run_registry.get_active_run.return_value = run_info

        # Act
        await recovery_service.handle_agent_execution_failure(
            work_item_id=work_item_id,
            board_id=board_id,
            error=error,
        )

        # Assert: Warning logged about missing event_store
        assert any(
            "event_store dependency not wired" in record.message and record.levelname == "WARNING"
            for record in caplog.records
        )
        assert any(record.error_id == "ERR_AGENT_EXECUTION_MISSING_EVENT_STORE" for record in caplog.records)

    @pytest.mark.asyncio
    async def test_completion_callback_failure_with_success_false_skips_dlq(self, recovery_service):
        """When success=False, DLQ queueing is skipped; only workflow failure occurs.

        This is the critical untested path: when agent execution failed (success=False)
        and then the completion callback also fails, we should NOT queue to DLQ
        (since the agent didn't succeed), but we should still fail the workflow run.
        """
        # Arrange
        work_item_id = "wi-1"
        board_id = "board-1"
        run_id = "run-1"
        stage_name = "coding"
        error = RuntimeError("Completion callback failed")

        run_info = ActiveRunInfo(
            work_item_id=work_item_id,
            run_id=run_id,
            stage_name=stage_name,
            project_id="proj-1",
        )
        recovery_service._run_registry.get_active_run.return_value = run_info

        # Act: Call with success=False (agent execution failed before callback)
        await recovery_service.handle_completion_callback_failure(
            work_item_id=work_item_id,
            board_id=board_id,
            success=False,  # Critical: execution already failed
            error=error,
        )

        # Assert: Work item should NOT be in dead letter queue
        stuck_items = recovery_service.get_stuck_work_items()
        assert work_item_id not in stuck_items, "Should not queue to DLQ when success=False"

        # Assert: Workflow should still be failed via _fail_workflow_run call
        # This assertion verifies that _fail_workflow_run was called (which emits WorkflowFailed).
        # The test inspects event_store.append calls to confirm the internal implementation
        # detail that _fail_workflow_run owns event persistence. This is acceptable because
        # _fail_workflow_run is a stable internal method and event persistence is its responsibility.
        assert recovery_service._event_store.append.called
        call_args = recovery_service._event_store.append.call_args
        events = call_args[0][1]
        # Should contain WorkflowFailed event only (not DLQ event) because success=False skips DLQ
        assert len(events) == 1
        assert events[0].work_item_id == work_item_id

    @pytest.mark.asyncio
    async def test_completion_callback_failure_with_success_true_queues_dlq(self, recovery_service):
        """When success=True, DLQ queueing occurs; agent execution was successful."""
        # Arrange
        work_item_id = "wi-1"
        board_id = "board-1"
        run_id = "run-1"
        stage_name = "coding"
        error = RuntimeError("Auto-progression callback failed")

        run_info = ActiveRunInfo(
            work_item_id=work_item_id,
            run_id=run_id,
            stage_name=stage_name,
            project_id="proj-1",
        )
        recovery_service._run_registry.get_active_run.return_value = run_info

        # Act: Call with success=True (agent execution succeeded but callback failed)
        await recovery_service.handle_completion_callback_failure(
            work_item_id=work_item_id,
            board_id=board_id,
            success=True,  # Execution succeeded, callback failed
            error=error,
        )

        # Assert: Work item SHOULD be in dead letter queue
        stuck_items = recovery_service.get_stuck_work_items()
        assert work_item_id in stuck_items, "Should queue to DLQ when success=True"

        # Assert: Workflow should also be failed
        assert recovery_service._event_store.append.called
