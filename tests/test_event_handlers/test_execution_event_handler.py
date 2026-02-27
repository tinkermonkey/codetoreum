"""Unit tests for ExecutionEventHandler."""

from unittest.mock import AsyncMock, Mock

import pytest

from codetoreum.application.event_handlers.execution_event_handler import (
    ExecutionEventHandler,
)
from codetoreum.domain.events import (
    ExecutionCompleted,
    ExecutionFailed,
    ExecutionInitialized,
    ExecutionStarted,
    ExecutionTimeout,
)


class MockExecutionService:
    """Mock execution service for testing."""

    def __init__(self):
        """Initialize mock."""
        self.initialized_events = []
        self.started_events = []
        self.completed_events = []
        self.failed_events = []
        self.timed_out_events = []


class TestExecutionEventHandler:
    """Tests for ExecutionEventHandler."""

    def test_initialization(self):
        """Test handler initialization."""
        service = MockExecutionService()
        handler = ExecutionEventHandler(service)

        assert handler.execution_service is service
        assert handler._metrics["total_executions"] == 0
        assert handler._metrics["active_executions"] == 0
        assert handler._metrics["completed_executions"] == 0
        assert handler._metrics["failed_executions"] == 0
        assert handler._metrics["timed_out_executions"] == 0
        assert len(handler._active_executions) == 0

    @pytest.mark.asyncio
    async def test_handle_execution_initialized(self):
        """Test handling ExecutionInitialized event."""
        service = MockExecutionService()
        handler = ExecutionEventHandler(service)

        event = ExecutionInitialized(
            aggregate_id="exec-123",
            payload={
                "agent_id": "agent-456",
                "work_item_id": "work-789",
                "workflow_id": "workflow-111",
                "stage_name": "implementation",
                "model": "claude-3-sonnet",
            },
        )

        await handler.handle(event)

        assert handler._metrics["total_executions"] == 1
        assert handler._metrics["active_executions"] == 0

    @pytest.mark.asyncio
    async def test_handle_execution_started(self):
        """Test handling ExecutionStarted event."""
        service = MockExecutionService()
        handler = ExecutionEventHandler(service)

        # Initialize execution first
        init_event = ExecutionInitialized(
            aggregate_id="exec-123",
            payload={
                "agent_id": "agent-456",
                "work_item_id": "work-789",
                "workflow_id": "workflow-111",
                "stage_name": "implementation",
            },
        )
        await handler.handle(init_event)

        # Start execution
        start_event = ExecutionStarted(
            aggregate_id="exec-123",
            payload={
                "started_at": "2025-01-14T10:30:00+00:00",
                "container_name": "container-123",
            },
        )
        await handler.handle(start_event)

        assert handler._metrics["active_executions"] == 1
        assert "exec-123" in handler._active_executions

    @pytest.mark.asyncio
    async def test_handle_execution_completed(self):
        """Test handling ExecutionCompleted event."""
        service = MockExecutionService()
        handler = ExecutionEventHandler(service)

        # Initialize and start
        await handler.handle(
            ExecutionInitialized(
                aggregate_id="exec-123",
                payload={
                    "agent_id": "agent-456",
                    "work_item_id": "work-789",
                    "workflow_id": "workflow-111",
                    "stage_name": "implementation",
                },
            )
        )

        await handler.handle(
            ExecutionStarted(
                aggregate_id="exec-123",
                payload={
                    "started_at": "2025-01-14T10:30:00+00:00",
                    "container_name": "container-123",
                },
            )
        )

        # Complete execution
        complete_event = ExecutionCompleted(
            aggregate_id="exec-123",
            payload={
                "completed_at": "2025-01-14T10:35:00+00:00",
                "input_tokens": 1000,
                "output_tokens": 500,
                "duration_seconds": 300.5,
            },
        )
        await handler.handle(complete_event)

        assert handler._metrics["completed_executions"] == 1
        assert handler._metrics["active_executions"] == 0
        assert "exec-123" not in handler._active_executions

    @pytest.mark.asyncio
    async def test_handle_execution_failed(self):
        """Test handling ExecutionFailed event."""
        service = MockExecutionService()
        handler = ExecutionEventHandler(service)

        # Initialize
        await handler.handle(
            ExecutionInitialized(
                aggregate_id="exec-123",
                payload={
                    "agent_id": "agent-456",
                    "work_item_id": "work-789",
                    "workflow_id": "workflow-111",
                    "stage_name": "implementation",
                },
            )
        )

        # Fail execution
        failed_event = ExecutionFailed(
            aggregate_id="exec-123",
            payload={
                "failed_at": "2025-01-14T10:35:00+00:00",
                "error_message": "Container crashed",
                "exit_code": 1,
                "duration_seconds": 10.5,
            },
        )
        await handler.handle(failed_event)

        assert handler._metrics["failed_executions"] == 1
        assert handler._metrics["total_executions"] == 1

    @pytest.mark.asyncio
    async def test_handle_execution_timeout(self):
        """Test handling ExecutionTimeout event."""
        service = MockExecutionService()
        handler = ExecutionEventHandler(service)

        # Initialize
        await handler.handle(
            ExecutionInitialized(
                aggregate_id="exec-123",
                payload={
                    "agent_id": "agent-456",
                    "work_item_id": "work-789",
                    "workflow_id": "workflow-111",
                    "stage_name": "implementation",
                },
            )
        )

        # Timeout execution
        timeout_event = ExecutionTimeout(
            aggregate_id="exec-123",
            payload={
                "timed_out_at": "2025-01-14T10:40:00+00:00",
                "timeout_seconds": 300.0,
                "error_message": "Execution timeout",
            },
        )
        await handler.handle(timeout_event)

        assert handler._metrics["timed_out_executions"] == 1

    @pytest.mark.asyncio
    async def test_metrics_tracking_multiple_executions(self):
        """Test metrics tracking for multiple executions."""
        service = MockExecutionService()
        handler = ExecutionEventHandler(service)

        # Create multiple executions
        for i in range(5):
            await handler.handle(
                ExecutionInitialized(
                    aggregate_id=f"exec-{i}",
                    payload={
                        "agent_id": "agent-456",
                        "work_item_id": f"work-{i}",
                        "workflow_id": "workflow-111",
                        "stage_name": "implementation",
                    },
                )
            )

        assert handler._metrics["total_executions"] == 5

        # Start some
        for i in range(3):
            await handler.handle(
                ExecutionStarted(
                    aggregate_id=f"exec-{i}",
                    payload={
                        "started_at": "2025-01-14T10:30:00+00:00",
                        "container_name": f"container-{i}",
                    },
                )
            )

        assert handler._metrics["active_executions"] == 3

        # Complete some
        for i in range(2):
            await handler.handle(
                ExecutionCompleted(
                    aggregate_id=f"exec-{i}",
                    payload={
                        "completed_at": "2025-01-14T10:35:00+00:00",
                        "input_tokens": 1000,
                        "output_tokens": 500,
                        "duration_seconds": 300.5,
                    },
                )
            )

        assert handler._metrics["completed_executions"] == 2
        assert handler._metrics["active_executions"] == 1

    @pytest.mark.asyncio
    async def test_active_executions_tracking(self):
        """Test tracking of active executions by ID."""
        service = MockExecutionService()
        handler = ExecutionEventHandler(service)

        # Initialize and start multiple executions
        for i in range(3):
            await handler.handle(
                ExecutionInitialized(
                    aggregate_id=f"exec-{i}",
                    payload={
                        "agent_id": f"agent-{i}",
                        "work_item_id": f"work-{i}",
                        "workflow_id": "workflow-111",
                        "stage_name": "implementation",
                    },
                )
            )

            await handler.handle(
                ExecutionStarted(
                    aggregate_id=f"exec-{i}",
                    payload={
                        "started_at": "2025-01-14T10:30:00+00:00",
                        "container_name": f"container-{i}",
                    },
                )
            )

        # Verify active executions
        assert len(handler._active_executions) == 3
        for i in range(3):
            assert f"exec-{i}" in handler._active_executions

    @pytest.mark.asyncio
    async def test_handle_unknown_event_type(self):
        """Test handling of unknown event type."""
        service = MockExecutionService()
        handler = ExecutionEventHandler(service)

        # Create a mock event of unknown type
        from codetoreum.domain.events import WorkItemCreated

        unknown_event = WorkItemCreated(
            aggregate_id="work-123",
            payload={
                "title": "Test Work Item",
                "description": "Test description",
                "project_id": "proj-123",
            },
        )

        # Should not raise, but log warning
        await handler.handle(unknown_event)

        # Metrics should remain unchanged
        assert handler._metrics["total_executions"] == 0

    @pytest.mark.asyncio
    async def test_execution_lifecycle_complete(self):
        """Test complete execution lifecycle."""
        service = MockExecutionService()
        handler = ExecutionEventHandler(service)

        # Step 1: Initialize
        await handler.handle(
            ExecutionInitialized(
                aggregate_id="exec-123",
                payload={
                    "agent_id": "agent-456",
                    "work_item_id": "work-789",
                    "workflow_id": "workflow-111",
                    "stage_name": "implementation",
                },
            )
        )
        assert handler._metrics["total_executions"] == 1
        assert handler._metrics["active_executions"] == 0

        # Step 2: Start
        await handler.handle(
            ExecutionStarted(
                aggregate_id="exec-123",
                payload={
                    "started_at": "2025-01-14T10:30:00+00:00",
                    "container_name": "container-123",
                },
            )
        )
        assert handler._metrics["active_executions"] == 1

        # Step 3: Complete
        await handler.handle(
            ExecutionCompleted(
                aggregate_id="exec-123",
                payload={
                    "completed_at": "2025-01-14T10:35:00+00:00",
                    "input_tokens": 1000,
                    "output_tokens": 500,
                    "duration_seconds": 300.5,
                },
            )
        )
        assert handler._metrics["completed_executions"] == 1
        assert handler._metrics["active_executions"] == 0

        # Verify final state
        assert handler._metrics["failed_executions"] == 0
        assert handler._metrics["timed_out_executions"] == 0
        assert "exec-123" not in handler._active_executions
