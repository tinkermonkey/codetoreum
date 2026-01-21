"""Unit tests for Execution Event Handler.

Tests the execution event handler with mock execution service to verify:
- Execution lifecycle tracking (initialized, started, completed, failed, timeout)
- Metric calculations (success rate, failure rate, timeout rate)
- Active execution tracking
- Proper logging and error handling
"""

from typing import Dict, List
from unittest.mock import AsyncMock, MagicMock

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


@pytest.fixture
def mock_execution_service():
    """Create mock execution service."""
    service = MagicMock(spec=ExecutionService)
    return service


@pytest.fixture
def handler(mock_execution_service):
    """Create execution event handler."""
    return ExecutionEventHandler(mock_execution_service)


class TestExecutionEventHandlerInitialization:
    """Tests for handler initialization and metrics setup."""

    def test_handler_initialization(self, handler):
        """Test handler initializes with zero metrics."""
        # Assert
        assert handler._metrics["total_executions"] == 0
        assert handler._metrics["active_executions"] == 0
        assert handler._metrics["completed_executions"] == 0
        assert handler._metrics["failed_executions"] == 0
        assert handler._metrics["timed_out_executions"] == 0
        assert len(handler._active_executions) == 0

    def test_get_metrics_initial(self, handler):
        """Test get_metrics returns initialized metrics."""
        # Act
        metrics = handler.get_metrics()

        # Assert
        assert metrics["total_executions"] == 0
        assert metrics["completed_executions"] == 0
        assert metrics["failed_executions"] == 0
        assert metrics["success_rate"] == 0.0
        assert metrics["failure_rate"] == 0.0
        assert metrics["timeout_rate"] == 0.0

    def test_get_active_executions_initial(self, handler):
        """Test get_active_executions returns empty dict initially."""
        # Act
        active = handler.get_active_executions()

        # Assert
        assert active == {}
        assert isinstance(active, dict)


class TestExecutionInitializedEvent:
    """Tests for ExecutionInitialized event handling."""

    async def test_handle_execution_initialized(self, handler):
        """Test handling of ExecutionInitialized event."""
        # Arrange
        event = ExecutionInitialized(
            aggregate_id="exec-123",
            payload={
                "agent_id": "agent-1",
                "work_item_id": "wi-456",
                "workflow_id": "wf-789",
                "stage_name": "review",
            },
        )

        # Act
        await handler.handle(event)

        # Assert
        assert handler._metrics["total_executions"] == 1
        assert handler._metrics["active_executions"] == 0
        assert handler._metrics["completed_executions"] == 0

    async def test_handle_multiple_execution_initialized(self, handler):
        """Test handling multiple ExecutionInitialized events."""
        # Arrange
        events = [
            ExecutionInitialized(
                aggregate_id=f"exec-{i}",
                payload={
                    "agent_id": f"agent-{i}",
                    "work_item_id": f"wi-{i}",
                    "workflow_id": "wf-789",
                    "stage_name": "review",
                },
            )
            for i in range(3)
        ]

        # Act
        for event in events:
            await handler.handle(event)

        # Assert
        assert handler._metrics["total_executions"] == 3
        assert handler.get_metrics()["total_executions"] == 3


class TestExecutionStartedEvent:
    """Tests for ExecutionStarted event handling."""

    async def test_handle_execution_started(self, handler):
        """Test handling of ExecutionStarted event."""
        # Arrange
        event = ExecutionStarted(
            aggregate_id="exec-123",
            payload={
                "container_name": "claude-code-exec-123",
                "pid": 12345,
            },
        )

        # Act
        await handler.handle(event)

        # Assert
        assert handler._metrics["active_executions"] == 1
        assert "exec-123" in handler._active_executions
        assert handler._active_executions["exec-123"] == "exec-123"

    async def test_handle_multiple_executions_started(self, handler):
        """Test multiple executions can be tracked concurrently."""
        # Arrange & Act
        for i in range(3):
            event = ExecutionStarted(
                aggregate_id=f"exec-{i}",
                payload={"container_name": f"claude-code-exec-{i}"},
            )
            await handler.handle(event)

        # Assert
        assert handler._metrics["active_executions"] == 3
        assert len(handler._active_executions) == 3
        for i in range(3):
            assert f"exec-{i}" in handler._active_executions


class TestExecutionCompletedEvent:
    """Tests for ExecutionCompleted event handling."""

    async def test_handle_execution_completed(self, handler):
        """Test handling of ExecutionCompleted event."""
        # Arrange - Set up initial state
        init_event = ExecutionInitialized(
            aggregate_id="exec-123",
            payload={
                "agent_id": "agent-1",
                "work_item_id": "wi-456",
                "workflow_id": "wf-789",
                "stage_name": "review",
            },
        )
        start_event = ExecutionStarted(
            aggregate_id="exec-123",
            payload={"container_name": "claude-code-exec-123"},
        )
        complete_event = ExecutionCompleted(
            aggregate_id="exec-123",
            payload={"input_tokens": 1000, "output_tokens": 2000},
        )

        # Act
        await handler.handle(init_event)
        await handler.handle(start_event)
        await handler.handle(complete_event)

        # Assert
        assert handler._metrics["completed_executions"] == 1
        assert handler._metrics["active_executions"] == 0
        assert "exec-123" not in handler._active_executions
        assert handler.get_metrics()["success_rate"] == 100.0

    async def test_execution_completed_updates_metrics_correctly(self, handler):
        """Test that completion properly updates all related metrics."""
        # Arrange - Initialize handler with 3 executions, start 3, complete 1
        for i in range(3):
            init = ExecutionInitialized(
                aggregate_id=f"exec-{i}",
                payload={
                    "agent_id": f"agent-{i}",
                    "work_item_id": f"wi-{i}",
                    "workflow_id": "wf-789",
                    "stage_name": "review",
                },
            )
            start = ExecutionStarted(
                aggregate_id=f"exec-{i}",
                payload={"container_name": f"claude-code-exec-{i}"},
            )
            await handler.handle(init)
            await handler.handle(start)

        # Complete first execution
        complete = ExecutionCompleted(
            aggregate_id="exec-0",
            payload={"input_tokens": 500, "output_tokens": 1500},
        )
        await handler.handle(complete)

        # Assert
        assert handler._metrics["total_executions"] == 3
        assert handler._metrics["active_executions"] == 2
        assert handler._metrics["completed_executions"] == 1
        assert handler.get_metrics()["success_rate"] == pytest.approx(33.33, abs=0.1)


class TestExecutionFailedEvent:
    """Tests for ExecutionFailed event handling."""

    async def test_handle_execution_failed(self, handler):
        """Test handling of ExecutionFailed event."""
        # Arrange - Set up initial state
        init_event = ExecutionInitialized(
            aggregate_id="exec-123",
            payload={
                "agent_id": "agent-1",
                "work_item_id": "wi-456",
                "workflow_id": "wf-789",
                "stage_name": "review",
            },
        )
        start_event = ExecutionStarted(
            aggregate_id="exec-123",
            payload={"container_name": "claude-code-exec-123"},
        )
        fail_event = ExecutionFailed(
            aggregate_id="exec-123",
            payload={
                "error_message": "Container crashed",
                "exit_code": 1,
            },
        )

        # Act
        await handler.handle(init_event)
        await handler.handle(start_event)
        await handler.handle(fail_event)

        # Assert
        assert handler._metrics["failed_executions"] == 1
        assert handler._metrics["active_executions"] == 0
        assert "exec-123" not in handler._active_executions
        assert handler.get_metrics()["failure_rate"] == 100.0

    async def test_multiple_executions_mixed_results(self, handler):
        """Test tracking mix of completed and failed executions."""
        # Arrange - 2 succeed, 2 fail
        for i in range(4):
            init = ExecutionInitialized(
                aggregate_id=f"exec-{i}",
                payload={
                    "agent_id": f"agent-{i}",
                    "work_item_id": f"wi-{i}",
                    "workflow_id": "wf-789",
                    "stage_name": "review",
                },
            )
            start = ExecutionStarted(
                aggregate_id=f"exec-{i}",
                payload={"container_name": f"claude-code-exec-{i}"},
            )
            await handler.handle(init)
            await handler.handle(start)

            if i < 2:
                complete = ExecutionCompleted(
                    aggregate_id=f"exec-{i}",
                    payload={"input_tokens": 100, "output_tokens": 200},
                )
                await handler.handle(complete)
            else:
                fail = ExecutionFailed(
                    aggregate_id=f"exec-{i}",
                    payload={
                        "error_message": f"Error {i}",
                        "exit_code": i,
                    },
                )
                await handler.handle(fail)

        # Assert
        metrics = handler.get_metrics()
        assert metrics["total_executions"] == 4
        assert metrics["completed_executions"] == 2
        assert metrics["failed_executions"] == 2
        assert metrics["active_executions"] == 0
        assert metrics["success_rate"] == 50.0
        assert metrics["failure_rate"] == 50.0


class TestExecutionTimeoutEvent:
    """Tests for ExecutionTimeout event handling."""

    async def test_handle_execution_timeout(self, handler):
        """Test handling of ExecutionTimeout event."""
        # Arrange - Set up initial state
        init_event = ExecutionInitialized(
            aggregate_id="exec-123",
            payload={
                "agent_id": "agent-1",
                "work_item_id": "wi-456",
                "workflow_id": "wf-789",
                "stage_name": "review",
            },
        )
        start_event = ExecutionStarted(
            aggregate_id="exec-123",
            payload={"container_name": "claude-code-exec-123"},
        )
        timeout_event = ExecutionTimeout(
            aggregate_id="exec-123",
            payload={},
        )

        # Act
        await handler.handle(init_event)
        await handler.handle(start_event)
        await handler.handle(timeout_event)

        # Assert
        assert handler._metrics["timed_out_executions"] == 1
        assert handler._metrics["failed_executions"] == 1
        assert handler._metrics["active_executions"] == 0
        assert "exec-123" not in handler._active_executions

    async def test_timeout_contributes_to_failure_metrics(self, handler):
        """Test that timeouts increment both failure and timeout counters."""
        # Arrange
        init = ExecutionInitialized(
            aggregate_id="exec-123",
            payload={
                "agent_id": "agent-1",
                "work_item_id": "wi-456",
                "workflow_id": "wf-789",
                "stage_name": "review",
            },
        )
        start = ExecutionStarted(
            aggregate_id="exec-123",
            payload={"container_name": "claude-code-exec-123"},
        )
        timeout = ExecutionTimeout(aggregate_id="exec-123", payload={})

        # Act
        await handler.handle(init)
        await handler.handle(start)
        await handler.handle(timeout)

        # Assert
        metrics = handler.get_metrics()
        assert metrics["timed_out_executions"] == 1
        assert metrics["failed_executions"] == 1
        assert metrics["timeout_rate"] == 100.0


class TestExecutionMetricsCalculation:
    """Tests for metric calculation methods."""

    async def test_success_rate_calculation(self, handler):
        """Test success rate is calculated correctly."""
        # Arrange - 3 total, 2 succeeded
        for i in range(3):
            init = ExecutionInitialized(
                aggregate_id=f"exec-{i}",
                payload={
                    "agent_id": f"agent-{i}",
                    "work_item_id": f"wi-{i}",
                    "workflow_id": "wf-789",
                    "stage_name": "review",
                },
            )
            start = ExecutionStarted(
                aggregate_id=f"exec-{i}",
                payload={"container_name": f"claude-code-exec-{i}"},
            )
            await handler.handle(init)
            await handler.handle(start)

            if i < 2:
                complete = ExecutionCompleted(
                    aggregate_id=f"exec-{i}",
                    payload={"input_tokens": 100, "output_tokens": 200},
                )
                await handler.handle(complete)

        # Act
        success_rate = handler._get_success_rate()

        # Assert
        assert success_rate == pytest.approx(66.66, abs=0.1)

    def test_success_rate_zero_executions(self, handler):
        """Test success rate with no executions."""
        # Act
        rate = handler._get_success_rate()

        # Assert
        assert rate == 0.0

    def test_failure_rate_calculation(self, handler):
        """Test failure rate is calculated correctly."""
        # Arrange - manually set metrics
        handler._metrics["total_executions"] = 10
        handler._metrics["failed_executions"] = 3

        # Act
        failure_rate = handler._get_failure_rate()

        # Assert
        assert failure_rate == 30.0

    def test_timeout_rate_calculation(self, handler):
        """Test timeout rate is calculated correctly."""
        # Arrange
        handler._metrics["total_executions"] = 20
        handler._metrics["timed_out_executions"] = 5

        # Act
        timeout_rate = handler._get_timeout_rate()

        # Assert
        assert timeout_rate == 25.0

    def test_timeout_rate_zero_total(self, handler):
        """Test timeout rate with no executions."""
        # Act
        rate = handler._get_timeout_rate()

        # Assert
        assert rate == 0.0


class TestExecutionEventHandlerErrors:
    """Tests for error handling in event handler."""

    async def test_handle_unexpected_event_type(self, handler):
        """Test handling of unexpected event type."""
        # Arrange - Create a different event type
        from codetoreum.domain.events import WorkItemCreated

        event = WorkItemCreated(
            aggregate_id="wi-123",
            payload={"title": "Test"},
        )

        # Act - Should not raise, just log warning
        await handler.handle(event)

        # Assert - Should not change any metrics
        assert handler._metrics["total_executions"] == 0

    async def test_completion_removes_from_active_tracking(self, handler):
        """Test that completion properly removes execution from active tracking."""
        # Arrange
        exec_id = "exec-123"
        init = ExecutionInitialized(
            aggregate_id=exec_id,
            payload={
                "agent_id": "agent-1",
                "work_item_id": "wi-456",
                "workflow_id": "wf-789",
                "stage_name": "review",
            },
        )
        start = ExecutionStarted(
            aggregate_id=exec_id,
            payload={"container_name": "claude-code-exec-123"},
        )
        complete = ExecutionCompleted(
            aggregate_id=exec_id,
            payload={"input_tokens": 100, "output_tokens": 200},
        )

        # Act
        await handler.handle(init)
        await handler.handle(start)
        assert exec_id in handler._active_executions  # Verify tracking
        await handler.handle(complete)

        # Assert
        assert exec_id not in handler._active_executions

    async def test_failure_removes_from_active_tracking(self, handler):
        """Test that failure properly removes execution from active tracking."""
        # Arrange
        exec_id = "exec-456"
        init = ExecutionInitialized(
            aggregate_id=exec_id,
            payload={
                "agent_id": "agent-1",
                "work_item_id": "wi-456",
                "workflow_id": "wf-789",
                "stage_name": "review",
            },
        )
        start = ExecutionStarted(
            aggregate_id=exec_id,
            payload={"container_name": "claude-code-exec-456"},
        )
        fail = ExecutionFailed(
            aggregate_id=exec_id,
            payload={"error_message": "Failed", "exit_code": 1},
        )

        # Act
        await handler.handle(init)
        await handler.handle(start)
        assert exec_id in handler._active_executions
        await handler.handle(fail)

        # Assert
        assert exec_id not in handler._active_executions


class TestExecutionEventHandlerConcurrency:
    """Tests for concurrent execution handling."""

    async def test_concurrent_executions_tracked_independently(self, handler):
        """Test multiple concurrent executions are tracked independently."""
        # Arrange - Start 3 concurrent executions
        exec_ids = ["exec-a", "exec-b", "exec-c"]
        for exec_id in exec_ids:
            init = ExecutionInitialized(
                aggregate_id=exec_id,
                payload={
                    "agent_id": f"agent-{exec_id}",
                    "work_item_id": f"wi-{exec_id}",
                    "workflow_id": "wf-789",
                    "stage_name": "review",
                },
            )
            start = ExecutionStarted(
                aggregate_id=exec_id,
                payload={"container_name": f"claude-code-{exec_id}"},
            )
            await handler.handle(init)
            await handler.handle(start)

        # Act - Complete middle execution
        complete = ExecutionCompleted(
            aggregate_id="exec-b",
            payload={"input_tokens": 100, "output_tokens": 200},
        )
        await handler.handle(complete)

        # Assert
        assert handler._metrics["active_executions"] == 2
        assert "exec-a" in handler._active_executions
        assert "exec-b" not in handler._active_executions
        assert "exec-c" in handler._active_executions
