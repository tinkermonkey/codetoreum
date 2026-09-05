"""Unit tests for ExecutionEventHandler."""

from unittest.mock import Mock

import pytest

from codetoreum.application.event_handlers.execution_event_handler import (
    ExecutionEventHandler,
)
from codetoreum.application.execution_service import ExecutionService
from codetoreum.domain.events import (
    ExecutionCompletedEvent,
    ExecutionFailedEvent,
    ExecutionInitializedEvent,
    ExecutionStartedEvent,
    ExecutionTimedOutEvent,
)
from codetoreum.domain.events.adapter_events import now_iso


def _initialized(exec_id: str, agent_id: str = "agent-1", work_item_id: str = "wi-1") -> ExecutionInitializedEvent:
    return ExecutionInitializedEvent(
        type="execution.initialized",
        timestamp=now_iso(),
        source="test",
        execution_id=exec_id,
        agent_id=agent_id,
        work_item_id=work_item_id,
        stage_name="Development",
    )


def _started(exec_id: str, work_item_id: str = "wi-1", agent_id: str = "agent-1") -> ExecutionStartedEvent:
    return ExecutionStartedEvent(
        type="execution.started",
        timestamp=now_iso(),
        source="test",
        execution_id=exec_id,
        work_item_id=work_item_id,
        agent_id=agent_id,
    )


def _completed(exec_id: str, work_item_id: str = "wi-1", agent_id: str = "agent-1") -> ExecutionCompletedEvent:
    return ExecutionCompletedEvent(
        type="execution.completed",
        timestamp=now_iso(),
        source="test",
        execution_id=exec_id,
        work_item_id=work_item_id,
        agent_id=agent_id,
        input_tokens=100,
        output_tokens=200,
    )


def _failed(
    exec_id: str, error: str = "Test failed", work_item_id: str = "wi-1", agent_id: str = "agent-1"
) -> ExecutionFailedEvent:
    return ExecutionFailedEvent(
        type="execution.failed",
        timestamp=now_iso(),
        source="test",
        execution_id=exec_id,
        work_item_id=work_item_id,
        agent_id=agent_id,
        error=error,
        exit_code=1,
    )


def _timed_out(exec_id: str, work_item_id: str = "wi-1") -> ExecutionTimedOutEvent:
    return ExecutionTimedOutEvent(
        type="execution.timed_out",
        timestamp=now_iso(),
        source="test",
        execution_id=exec_id,
        work_item_id=work_item_id,
        timeout_seconds=60,
        started_at=now_iso(),
    )


class TestExecutionEventHandlerInitialization:
    """Test ExecutionEventHandler initialization."""

    def test_handler_initialization(self):
        """Test handler initializes with execution service."""
        mock_service = Mock(spec=ExecutionService)
        handler = ExecutionEventHandler(mock_service)

        assert handler.execution_service is mock_service
        assert handler._metrics == {
            "total_executions": 0,
            "active_executions": 0,
            "completed_executions": 0,
            "failed_executions": 0,
            "timed_out_executions": 0,
        }
        assert handler._active_executions == {}
        mock_service.assert_not_called()

    def test_handler_has_event_types(self):
        """Test handler is decorated with correct event types."""
        mock_service = Mock(spec=ExecutionService)
        handler = ExecutionEventHandler(mock_service)

        event_types = handler.get_event_types()
        assert "ExecutionInitializedEvent" in event_types
        assert "ExecutionStartedEvent" in event_types
        assert "ExecutionCompletedEvent" in event_types
        assert "ExecutionFailedEvent" in event_types
        assert "ExecutionTimedOutEvent" in event_types


@pytest.mark.asyncio
class TestExecutionEventHandlerMethods:
    """Test ExecutionEventHandler event handling methods."""

    async def test_handle_execution_initialized(self):
        """Test handling ExecutionInitializedEvent."""
        mock_service = Mock(spec=ExecutionService)
        handler = ExecutionEventHandler(mock_service)

        await handler.handle(_initialized("exec-1"))

        assert handler._metrics["total_executions"] == 1
        assert handler._metrics["active_executions"] == 0

    async def test_handle_execution_started(self):
        """Test handling ExecutionStartedEvent."""
        mock_service = Mock(spec=ExecutionService)
        handler = ExecutionEventHandler(mock_service)

        await handler.handle(_started("exec-1"))

        assert handler._metrics["active_executions"] == 1
        assert "exec-1" in handler._active_executions
        assert handler._active_executions["exec-1"] == "exec-1"

    async def test_handle_execution_completed(self):
        """Test handling ExecutionCompletedEvent."""
        mock_service = Mock(spec=ExecutionService)
        handler = ExecutionEventHandler(mock_service)

        handler._metrics["total_executions"] = 1
        handler._metrics["active_executions"] = 1
        handler._active_executions["exec-1"] = "exec-1"

        await handler.handle(_completed("exec-1"))

        assert handler._metrics["completed_executions"] == 1
        assert handler._metrics["active_executions"] == 0
        assert "exec-1" not in handler._active_executions

    async def test_handle_execution_failed(self):
        """Test handling ExecutionFailedEvent."""
        mock_service = Mock(spec=ExecutionService)
        handler = ExecutionEventHandler(mock_service)

        handler._metrics["total_executions"] = 1
        handler._metrics["active_executions"] = 1
        handler._active_executions["exec-1"] = "exec-1"

        await handler.handle(_failed("exec-1", "Test failed"))

        assert handler._metrics["failed_executions"] == 1
        assert handler._metrics["active_executions"] == 0
        assert "exec-1" not in handler._active_executions

    async def test_handle_execution_timeout(self):
        """Test handling ExecutionTimedOutEvent."""
        mock_service = Mock(spec=ExecutionService)
        handler = ExecutionEventHandler(mock_service)

        handler._metrics["total_executions"] = 1
        handler._metrics["active_executions"] = 1
        handler._active_executions["exec-1"] = "exec-1"

        await handler.handle(_timed_out("exec-1"))

        assert handler._metrics["timed_out_executions"] == 1
        assert handler._metrics["failed_executions"] == 1
        assert handler._metrics["active_executions"] == 0
        assert "exec-1" not in handler._active_executions

    async def test_handle_unexpected_event(self):
        """Test handling unexpected event type."""
        mock_service = Mock(spec=ExecutionService)
        handler = ExecutionEventHandler(mock_service)

        event = Mock()
        event.event_type = "UnexpectedEvent"
        await handler.handle(event)

        assert handler._metrics["total_executions"] == 0


@pytest.mark.asyncio
class TestExecutionEventHandlerMetrics:
    """Test ExecutionEventHandler metrics calculations."""

    async def test_get_metrics_initial_state(self):
        """Test get_metrics returns correct initial state."""
        mock_service = Mock(spec=ExecutionService)
        handler = ExecutionEventHandler(mock_service)

        metrics = handler.get_metrics()

        assert metrics["total_executions"] == 0
        assert metrics["active_executions"] == 0
        assert metrics["completed_executions"] == 0
        assert metrics["failed_executions"] == 0
        assert metrics["timed_out_executions"] == 0
        assert metrics["success_rate"] == 0.0
        assert metrics["failure_rate"] == 0.0
        assert metrics["timeout_rate"] == 0.0

    async def test_success_rate_calculation(self):
        """Test success rate calculation."""
        mock_service = Mock(spec=ExecutionService)
        handler = ExecutionEventHandler(mock_service)

        handler._metrics["total_executions"] = 10
        handler._metrics["completed_executions"] = 8

        metrics = handler.get_metrics()
        assert metrics["success_rate"] == 80.0

    async def test_failure_rate_calculation(self):
        """Test failure rate calculation."""
        mock_service = Mock(spec=ExecutionService)
        handler = ExecutionEventHandler(mock_service)

        handler._metrics["total_executions"] = 10
        handler._metrics["failed_executions"] = 2

        metrics = handler.get_metrics()
        assert metrics["failure_rate"] == 20.0

    async def test_timeout_rate_calculation(self):
        """Test timeout rate calculation."""
        mock_service = Mock(spec=ExecutionService)
        handler = ExecutionEventHandler(mock_service)

        handler._metrics["total_executions"] = 10
        handler._metrics["timed_out_executions"] = 3

        metrics = handler.get_metrics()
        assert metrics["timeout_rate"] == 30.0

    async def test_metrics_with_zero_total_executions(self):
        """Test metrics when no executions have occurred."""
        mock_service = Mock(spec=ExecutionService)
        handler = ExecutionEventHandler(mock_service)

        handler._metrics["total_executions"] = 0
        metrics = handler.get_metrics()
        assert metrics["success_rate"] == 0.0
        assert metrics["failure_rate"] == 0.0
        assert metrics["timeout_rate"] == 0.0


@pytest.mark.asyncio
class TestExecutionEventHandlerActiveExecutions:
    """Test ExecutionEventHandler active execution tracking."""

    async def test_get_active_executions_empty(self):
        """Test get_active_executions returns empty dict initially."""
        mock_service = Mock(spec=ExecutionService)
        handler = ExecutionEventHandler(mock_service)

        assert handler.get_active_executions() == {}

    async def test_get_active_executions_populated(self):
        """Test get_active_executions returns tracking data."""
        mock_service = Mock(spec=ExecutionService)
        handler = ExecutionEventHandler(mock_service)

        handler._active_executions["exec-1"] = "exec-1"
        handler._active_executions["exec-2"] = "exec-2"

        active = handler.get_active_executions()
        assert len(active) == 2
        assert "exec-1" in active
        assert "exec-2" in active

    async def test_get_active_executions_returns_copy(self):
        """Test get_active_executions returns a copy, not reference."""
        mock_service = Mock(spec=ExecutionService)
        handler = ExecutionEventHandler(mock_service)

        handler._active_executions["exec-1"] = "exec-1"

        active = handler.get_active_executions()
        active["exec-2"] = "exec-2"

        assert len(handler._active_executions) == 1
        assert "exec-2" not in handler._active_executions


@pytest.mark.asyncio
class TestExecutionEventHandlerWorkflow:
    """Test ExecutionEventHandler in realistic workflows."""

    async def test_complete_execution_workflow(self):
        """Test a complete execution workflow (initialized -> started -> completed)."""
        mock_service = Mock(spec=ExecutionService)
        handler = ExecutionEventHandler(mock_service)

        await handler.handle(_initialized("exec-1"))
        assert handler._metrics["total_executions"] == 1

        await handler.handle(_started("exec-1"))
        assert handler._metrics["active_executions"] == 1

        await handler.handle(_completed("exec-1"))
        assert handler._metrics["completed_executions"] == 1
        assert handler._metrics["active_executions"] == 0
        assert handler.get_metrics()["success_rate"] == 100.0

    async def test_multiple_concurrent_executions(self):
        """Test multiple concurrent executions."""
        mock_service = Mock(spec=ExecutionService)
        handler = ExecutionEventHandler(mock_service)

        for i in range(5):
            await handler.handle(_initialized(f"exec-{i}", agent_id=f"agent-{i}"))
            await handler.handle(_started(f"exec-{i}"))

        assert handler._metrics["total_executions"] == 5
        assert handler._metrics["active_executions"] == 5
        assert len(handler.get_active_executions()) == 5

        for i in range(3):
            await handler.handle(_completed(f"exec-{i}"))

        assert handler._metrics["completed_executions"] == 3
        assert handler._metrics["active_executions"] == 2
        assert handler.get_metrics()["success_rate"] == 60.0

    async def test_execution_failure_workflow(self):
        """Test execution failure workflow."""
        mock_service = Mock(spec=ExecutionService)
        handler = ExecutionEventHandler(mock_service)

        await handler.handle(_initialized("exec-1"))
        await handler.handle(_started("exec-1"))
        await handler.handle(_failed("exec-1", "Container crashed"))

        assert handler._metrics["failed_executions"] == 1
        assert handler._metrics["active_executions"] == 0
        assert handler.get_metrics()["failure_rate"] == 100.0

    async def test_execution_timeout_workflow(self):
        """Test execution timeout workflow."""
        mock_service = Mock(spec=ExecutionService)
        handler = ExecutionEventHandler(mock_service)

        await handler.handle(_initialized("exec-1"))
        await handler.handle(_started("exec-1"))
        await handler.handle(_timed_out("exec-1"))

        assert handler._metrics["timed_out_executions"] == 1
        assert handler._metrics["failed_executions"] == 1
        assert handler._metrics["active_executions"] == 0
        assert handler.get_metrics()["timeout_rate"] == 100.0

    async def test_mixed_outcome_metrics(self):
        """Test metrics with mixed success/failure outcomes."""
        mock_service = Mock(spec=ExecutionService)
        handler = ExecutionEventHandler(mock_service)

        outcomes = [
            ("exec-1", "completed"),
            ("exec-2", "completed"),
            ("exec-3", "completed"),
            ("exec-4", "completed"),
            ("exec-5", "completed"),
            ("exec-6", "completed"),
            ("exec-7", "failed"),
            ("exec-8", "failed"),
            ("exec-9", "timed_out"),
            ("exec-10", "timed_out"),
        ]

        for exec_id, outcome in outcomes:
            await handler.handle(_initialized(exec_id))
            await handler.handle(_started(exec_id))

            if outcome == "completed":
                await handler.handle(_completed(exec_id))
            elif outcome == "failed":
                await handler.handle(_failed(exec_id, "Failed"))
            else:
                await handler.handle(_timed_out(exec_id))

        metrics = handler.get_metrics()
        assert metrics["total_executions"] == 10
        assert metrics["completed_executions"] == 6
        assert metrics["failed_executions"] == 4  # 2 failed + 2 timeout
        assert metrics["timed_out_executions"] == 2
        assert metrics["success_rate"] == 60.0
        assert metrics["failure_rate"] == 40.0
        assert metrics["timeout_rate"] == 20.0
