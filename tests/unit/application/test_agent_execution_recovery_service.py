"""Unit tests for AgentExecutionRecoveryService.

Tests recovery mechanisms for:
1. Completion callback failures (auto-progression stuck)
2. Agent execution failures (lock release failures)
"""

from unittest.mock import AsyncMock, MagicMock

import pytest

from codetoreum.application.agent_execution_recovery_service import (
    AgentExecutionRecoveryService,
    FailedAutoProgression,
)
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

        service = AgentExecutionRecoveryService(
            board_service=board_service,
            event_store=event_store,
            run_registry=run_registry,
        )
        service._board_service = board_service
        service._event_store = event_store
        service._run_registry = run_registry
        return service

    @pytest.mark.asyncio
    async def test_completion_callback_failure_queues_for_recovery(self, recovery_service):
        """When completion callback fails, work item is queued in dead letter queue."""
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

        # Assert: Work item in dead letter queue
        dlq = recovery_service.dead_letter_queue
        assert len(dlq) == 1
        assert dlq[0].work_item_id == work_item_id
        assert dlq[0].board_id == board_id
        assert dlq[0].from_column == "In Development"

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
        assert events[0].payload["work_item_id"] == work_item_id

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
        assert events[0].payload["work_item_id"] == work_item_id

    @pytest.mark.asyncio
    async def test_dead_letter_queue_can_be_cleared(self, recovery_service):
        """Dead letter queue can be cleared after processing."""
        # Arrange
        recovery_service._dead_letter_queue.append(
            FailedAutoProgression(
                work_item_id="wi-1",
                board_id="board-1",
                from_column="In Development",
                to_column="Review",
                reason="Auto-progression failed",
                failed_at=MagicMock(),
            )
        )
        assert len(recovery_service.dead_letter_queue) == 1

        # Act
        recovery_service.clear_dead_letter_queue()

        # Assert
        assert len(recovery_service.dead_letter_queue) == 0

    @pytest.mark.asyncio
    async def test_get_stuck_work_items_returns_dlq_items(self, recovery_service):
        """Get stuck work items returns all work items in dead letter queue."""
        # Arrange
        recovery_service._dead_letter_queue.append(
            FailedAutoProgression(
                work_item_id="wi-1",
                board_id="board-1",
                from_column="In Development",
                to_column="Review",
                reason="Auto-progression failed",
                failed_at=MagicMock(),
            )
        )
        recovery_service._dead_letter_queue.append(
            FailedAutoProgression(
                work_item_id="wi-2",
                board_id="board-1",
                from_column="In Development",
                to_column="Review",
                reason="Auto-progression failed",
                failed_at=MagicMock(),
            )
        )

        # Act
        stuck_items = recovery_service.get_stuck_work_items()

        # Assert
        assert stuck_items == ["wi-1", "wi-2"]

    @pytest.mark.asyncio
    async def test_failed_auto_progression_serialization(self):
        """FailedAutoProgression can be serialized to dict."""
        # Arrange
        from datetime import UTC, datetime

        failed = FailedAutoProgression(
            work_item_id="wi-1",
            board_id="board-1",
            from_column="In Development",
            to_column="Review",
            reason="Auto-progression failed",
            failed_at=datetime(2026, 3, 15, 12, 0, 0, tzinfo=UTC),
            attempt_count=1,
        )

        # Act
        serialized = failed.to_dict()

        # Assert
        assert serialized["work_item_id"] == "wi-1"
        assert serialized["board_id"] == "board-1"
        assert serialized["from_column"] == "In Development"
        assert serialized["to_column"] == "Review"
        assert serialized["attempt_count"] == 1
        assert "2026-03-15" in serialized["failed_at"]
