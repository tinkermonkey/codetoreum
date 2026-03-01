"""Unit tests for ExecutionEventHandler."""

from unittest.mock import AsyncMock, Mock

import pytest

from codetoreum.application.event_handlers.execution_event_handler import (
    ExecutionEventHandler,
)
from codetoreum.application.execution_service import ExecutionService
from codetoreum.domain.events import (
    ExecutionCompleted,
    ExecutionFailed,
    ExecutionInitialized,
    ExecutionStarted,
    ExecutionTimeout,
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
        # Verify service mock is not called during initialization
        mock_service.assert_not_called()

    def test_handler_has_event_types(self):
        """Test handler is decorated with correct event types."""
        mock_service = Mock(spec=ExecutionService)
        handler = ExecutionEventHandler(mock_service)

        # Verify handler has get_event_types method set by decorator
        event_types = handler.get_event_types()
        assert "ExecutionInitialized" in event_types
        assert "ExecutionStarted" in event_types
        assert "ExecutionCompleted" in event_types
        assert "ExecutionFailed" in event_types
        assert "ExecutionTimeout" in event_types


@pytest.mark.asyncio
class TestExecutionEventHandlerMethods:
    """Test ExecutionEventHandler event handling methods."""

    async def test_handle_execution_initialized(self):
        """Test handling ExecutionInitialized event."""
        mock_service = Mock(spec=ExecutionService)
        handler = ExecutionEventHandler(mock_service)

        event = ExecutionInitialized(
            aggregate_id="exec-1",
            payload={
                "agent_id": "agent-1",
                "work_item_id": "wi-1",
                "workflow_id": "wf-1",
                "stage_name": "Development",
            },
        )

        await handler.handle(event)

        assert handler._metrics["total_executions"] == 1
        assert handler._metrics["active_executions"] == 0

    async def test_handle_execution_started(self):
        """Test handling ExecutionStarted event."""
        mock_service = Mock(spec=ExecutionService)
        handler = ExecutionEventHandler(mock_service)

        event = ExecutionStarted(
            aggregate_id="exec-1",
            payload={"container_name": "container-1"},
        )

        await handler.handle(event)

        assert handler._metrics["active_executions"] == 1
        assert "exec-1" in handler._active_executions
        assert handler._active_executions["exec-1"] == "exec-1"

    async def test_handle_execution_completed(self):
        """Test handling ExecutionCompleted event."""
        mock_service = Mock(spec=ExecutionService)
        handler = ExecutionEventHandler(mock_service)

        # Initialize and start execution
        handler._metrics["total_executions"] = 1
        handler._metrics["active_executions"] = 1
        handler._active_executions["exec-1"] = "exec-1"

        event = ExecutionCompleted(
            aggregate_id="exec-1",
            payload={"input_tokens": 100, "output_tokens": 200},
        )

        await handler.handle(event)

        assert handler._metrics["completed_executions"] == 1
        assert handler._metrics["active_executions"] == 0
        assert "exec-1" not in handler._active_executions

    async def test_handle_execution_failed(self):
        """Test handling ExecutionFailed event."""
        mock_service = Mock(spec=ExecutionService)
        handler = ExecutionEventHandler(mock_service)

        # Initialize and start execution
        handler._metrics["total_executions"] = 1
        handler._metrics["active_executions"] = 1
        handler._active_executions["exec-1"] = "exec-1"

        event = ExecutionFailed(
            aggregate_id="exec-1",
            payload={
                "error_message": "Test failed",
                "exit_code": 1,
            },
        )

        await handler.handle(event)

        assert handler._metrics["failed_executions"] == 1
        assert handler._metrics["active_executions"] == 0
        assert "exec-1" not in handler._active_executions

    async def test_handle_execution_timeout(self):
        """Test handling ExecutionTimeout event."""
        mock_service = Mock(spec=ExecutionService)
        handler = ExecutionEventHandler(mock_service)

        # Initialize and start execution
        handler._metrics["total_executions"] = 1
        handler._metrics["active_executions"] = 1
        handler._active_executions["exec-1"] = "exec-1"

        event = ExecutionTimeout(
            aggregate_id="exec-1",
            payload={},
        )

        await handler.handle(event)

        assert handler._metrics["timed_out_executions"] == 1
        assert handler._metrics["failed_executions"] == 1
        assert handler._metrics["active_executions"] == 0
        assert "exec-1" not in handler._active_executions

    async def test_handle_unexpected_event(self):
        """Test handling unexpected event type."""
        mock_service = Mock(spec=ExecutionService)
        handler = ExecutionEventHandler(mock_service)

        # Create a mock event with unexpected type
        event = Mock()
        event.event_type = "UnexpectedEvent"

        # Should not raise, just log warning
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

        # Explicitly set total_executions to 0
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

        active = handler.get_active_executions()

        assert active == {}

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

        # Original should not be modified
        assert len(handler._active_executions) == 1
        assert "exec-2" not in handler._active_executions


@pytest.mark.asyncio
class TestExecutionEventHandlerWorkflow:
    """Test ExecutionEventHandler in realistic workflows."""

    async def test_complete_execution_workflow(self):
        """Test a complete execution workflow (initialized -> started -> completed)."""
        mock_service = Mock(spec=ExecutionService)
        handler = ExecutionEventHandler(mock_service)

        # Initialization event
        init_event = ExecutionInitialized(
            aggregate_id="exec-1",
            payload={
                "agent_id": "agent-1",
                "work_item_id": "wi-1",
                "workflow_id": "wf-1",
                "stage_name": "Development",
            },
        )
        await handler.handle(init_event)

        assert handler._metrics["total_executions"] == 1

        # Start event
        start_event = ExecutionStarted(
            aggregate_id="exec-1",
            payload={"container_name": "container-1"},
        )
        await handler.handle(start_event)

        assert handler._metrics["active_executions"] == 1

        # Completion event
        complete_event = ExecutionCompleted(
            aggregate_id="exec-1",
            payload={"input_tokens": 100, "output_tokens": 200},
        )
        await handler.handle(complete_event)

        assert handler._metrics["completed_executions"] == 1
        assert handler._metrics["active_executions"] == 0
        assert handler.get_metrics()["success_rate"] == 100.0

    async def test_multiple_concurrent_executions(self):
        """Test multiple concurrent executions."""
        mock_service = Mock(spec=ExecutionService)
        handler = ExecutionEventHandler(mock_service)

        # Start multiple executions
        for i in range(5):
            init_event = ExecutionInitialized(
                aggregate_id=f"exec-{i}",
                payload={"agent_id": f"agent-{i}"},
            )
            await handler.handle(init_event)

            start_event = ExecutionStarted(
                aggregate_id=f"exec-{i}",
                payload={},
            )
            await handler.handle(start_event)

        assert handler._metrics["total_executions"] == 5
        assert handler._metrics["active_executions"] == 5
        assert len(handler.get_active_executions()) == 5

        # Complete some executions
        for i in range(3):
            complete_event = ExecutionCompleted(
                aggregate_id=f"exec-{i}",
                payload={},
            )
            await handler.handle(complete_event)

        assert handler._metrics["completed_executions"] == 3
        assert handler._metrics["active_executions"] == 2
        assert handler.get_metrics()["success_rate"] == 60.0

    async def test_execution_failure_workflow(self):
        """Test execution failure workflow."""
        mock_service = Mock(spec=ExecutionService)
        handler = ExecutionEventHandler(mock_service)

        # Initialize and start
        init_event = ExecutionInitialized(
            aggregate_id="exec-1",
            payload={},
        )
        await handler.handle(init_event)

        start_event = ExecutionStarted(
            aggregate_id="exec-1",
            payload={},
        )
        await handler.handle(start_event)

        # Fail event
        fail_event = ExecutionFailed(
            aggregate_id="exec-1",
            payload={"error_message": "Container crashed", "exit_code": 139},
        )
        await handler.handle(fail_event)

        assert handler._metrics["failed_executions"] == 1
        assert handler._metrics["active_executions"] == 0
        assert handler.get_metrics()["failure_rate"] == 100.0

    async def test_execution_timeout_workflow(self):
        """Test execution timeout workflow."""
        mock_service = Mock(spec=ExecutionService)
        handler = ExecutionEventHandler(mock_service)

        # Initialize and start
        init_event = ExecutionInitialized(
            aggregate_id="exec-1",
            payload={},
        )
        await handler.handle(init_event)

        start_event = ExecutionStarted(
            aggregate_id="exec-1",
            payload={},
        )
        await handler.handle(start_event)

        # Timeout event
        timeout_event = ExecutionTimeout(
            aggregate_id="exec-1",
            payload={},
        )
        await handler.handle(timeout_event)

        assert handler._metrics["timed_out_executions"] == 1
        assert handler._metrics["failed_executions"] == 1
        assert handler._metrics["active_executions"] == 0
        assert handler.get_metrics()["timeout_rate"] == 100.0

    async def test_mixed_outcome_metrics(self):
        """Test metrics with mixed success/failure outcomes."""
        mock_service = Mock(spec=ExecutionService)
        handler = ExecutionEventHandler(mock_service)

        # Create 10 total executions with mixed outcomes
        # 6 successful, 2 failed, 2 timed out
        execution_outcomes = [
            ("exec-1", ExecutionCompleted),
            ("exec-2", ExecutionCompleted),
            ("exec-3", ExecutionCompleted),
            ("exec-4", ExecutionCompleted),
            ("exec-5", ExecutionCompleted),
            ("exec-6", ExecutionCompleted),
            ("exec-7", ExecutionFailed),
            ("exec-8", ExecutionFailed),
            ("exec-9", ExecutionTimeout),
            ("exec-10", ExecutionTimeout),
        ]

        for exec_id, event_type in execution_outcomes:
            # Initialize
            init_event = ExecutionInitialized(
                aggregate_id=exec_id,
                payload={},
            )
            await handler.handle(init_event)

            # Start
            start_event = ExecutionStarted(
                aggregate_id=exec_id,
                payload={},
            )
            await handler.handle(start_event)

            # Complete with specific outcome
            if event_type == ExecutionCompleted:
                complete_event = ExecutionCompleted(
                    aggregate_id=exec_id,
                    payload={},
                )
            elif event_type == ExecutionFailed:
                complete_event = ExecutionFailed(
                    aggregate_id=exec_id,
                    payload={"error_message": "Failed"},
                )
            else:  # ExecutionTimeout
                complete_event = ExecutionTimeout(
                    aggregate_id=exec_id,
                    payload={},
                )

            await handler.handle(complete_event)

        metrics = handler.get_metrics()
        assert metrics["total_executions"] == 10
        assert metrics["completed_executions"] == 6
        assert metrics["failed_executions"] == 4  # 2 failed + 2 timeout
        assert metrics["timed_out_executions"] == 2
        assert metrics["success_rate"] == 60.0
        assert metrics["failure_rate"] == 40.0
        assert metrics["timeout_rate"] == 20.0
