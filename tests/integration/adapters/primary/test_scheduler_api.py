"""
Integration tests for scheduler REST API endpoints.

Tests scheduler lifecycle, task scheduling, execution queue management,
schedule configuration updates, and health checks.
"""

import pytest
from datetime import datetime, timedelta
from typing import AsyncGenerator
from unittest.mock import AsyncMock, MagicMock

from fastapi import FastAPI, status
from fastapi.testclient import TestClient

from codetoreum.adapters.primary.routers.scheduler import create_scheduler_router
from codetoreum.ports.input.scheduler_command import ISchedulerCommandPort
from codetoreum.ports.input.scheduler_query import ISchedulerQueryPort


# ============================================================================
# Fixtures
# ============================================================================

@pytest.fixture
def mock_scheduler_command_port() -> AsyncMock:
    """Create mock scheduler command port for testing."""
    return AsyncMock(spec=ISchedulerCommandPort)


@pytest.fixture
def mock_scheduler_query_port() -> AsyncMock:
    """Create mock scheduler query port for testing."""
    return AsyncMock(spec=ISchedulerQueryPort)


@pytest.fixture
def test_app(
    mock_scheduler_command_port: AsyncMock,
    mock_scheduler_query_port: AsyncMock,
) -> FastAPI:
    """Create test FastAPI application with scheduler router."""
    app = FastAPI()

    router = create_scheduler_router(
        command_port=mock_scheduler_command_port,
        query_port=mock_scheduler_query_port,
        auth_deps=None,
    )

    app.include_router(router)
    return app


@pytest.fixture
def client(test_app: FastAPI) -> TestClient:
    """Create test client for making HTTP requests."""
    return TestClient(test_app)


# ============================================================================
# Scheduler Lifecycle Tests
# ============================================================================

class TestSchedulerLifecycle:
    """Tests for scheduler start, stop, pause, resume, and status."""

    @pytest.mark.asyncio
    async def test_start_scheduler(
        self,
        client: TestClient,
        mock_scheduler_command_port: AsyncMock,
    ):
        """Test starting the scheduler."""
        # Arrange
        mock_scheduler_command_port.start.return_value = {
            "status": "running",
            "started_at": datetime.utcnow().isoformat(),
        }

        # Act
        response = client.post("/api/v2/scheduler/start")

        # Assert
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["status"] == "running"

    @pytest.mark.asyncio
    async def test_start_scheduler_already_running(
        self,
        client: TestClient,
        mock_scheduler_command_port: AsyncMock,
    ):
        """Test starting scheduler when already running."""
        # Arrange
        mock_scheduler_command_port.start.side_effect = Exception(
            "Scheduler is already running"
        )

        # Act
        response = client.post("/api/v2/scheduler/start")

        # Assert
        assert response.status_code == status.HTTP_409_CONFLICT

    @pytest.mark.asyncio
    async def test_stop_scheduler(
        self,
        client: TestClient,
        mock_scheduler_command_port: AsyncMock,
    ):
        """Test stopping the scheduler."""
        # Arrange
        mock_scheduler_command_port.stop.return_value = {
            "status": "stopped",
            "stopped_at": datetime.utcnow().isoformat(),
        }

        # Act
        response = client.post("/api/v2/scheduler/stop")

        # Assert
        assert response.status_code == status.HTTP_200_OK

    @pytest.mark.asyncio
    async def test_pause_scheduler(
        self,
        client: TestClient,
        mock_scheduler_command_port: AsyncMock,
    ):
        """Test pausing the scheduler."""
        # Arrange
        mock_scheduler_command_port.pause.return_value = {
            "status": "paused",
        }

        # Act
        response = client.post("/api/v2/scheduler/pause")

        # Assert
        assert response.status_code == status.HTTP_200_OK

    @pytest.mark.asyncio
    async def test_resume_scheduler(
        self,
        client: TestClient,
        mock_scheduler_command_port: AsyncMock,
    ):
        """Test resuming the scheduler."""
        # Arrange
        mock_scheduler_command_port.resume.return_value = {
            "status": "running",
        }

        # Act
        response = client.post("/api/v2/scheduler/resume")

        # Assert
        assert response.status_code == status.HTTP_200_OK

    @pytest.mark.asyncio
    async def test_get_scheduler_status(
        self,
        client: TestClient,
        mock_scheduler_query_port: AsyncMock,
    ):
        """Test retrieving scheduler status."""
        # Arrange
        mock_scheduler_query_port.get_status.return_value = {
            "status": "running",
            "scheduled_tasks": 15,
            "queued_executions": 3,
            "uptime_seconds": 7200,
        }

        # Act
        response = client.get("/api/v2/scheduler/status")

        # Assert
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["status"] == "running"
        assert data["scheduled_tasks"] == 15


# ============================================================================
# Task Scheduling Tests
# ============================================================================

class TestTaskScheduling:
    """Tests for scheduling and managing tasks."""

    @pytest.mark.asyncio
    async def test_schedule_immediate_execution(
        self,
        client: TestClient,
        mock_scheduler_command_port: AsyncMock,
    ):
        """Test scheduling immediate execution."""
        # Arrange
        mock_scheduler_command_port.schedule_execution.return_value = {
            "schedule_id": "schedule-123",
            "execution_time": datetime.utcnow().isoformat(),
        }

        # Act
        response = client.post(
            "/api/v2/scheduler/schedule",
            json={
                "work_item_id": "work-item-123",
                "workflow_id": "workflow-123",
                "execute_at": "now",
            },
        )

        # Assert
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["schedule_id"] == "schedule-123"

    @pytest.mark.asyncio
    async def test_schedule_future_execution(
        self,
        client: TestClient,
        mock_scheduler_command_port: AsyncMock,
    ):
        """Test scheduling execution for future time."""
        # Arrange
        future_time = (datetime.utcnow() + timedelta(hours=2)).isoformat()
        mock_scheduler_command_port.schedule_execution.return_value = {
            "schedule_id": "schedule-456",
            "execution_time": future_time,
        }

        # Act
        response = client.post(
            "/api/v2/scheduler/schedule",
            json={
                "work_item_id": "work-item-456",
                "workflow_id": "workflow-123",
                "execute_at": future_time,
            },
        )

        # Assert
        assert response.status_code == status.HTTP_200_OK

    @pytest.mark.asyncio
    async def test_schedule_recurring_execution(
        self,
        client: TestClient,
        mock_scheduler_command_port: AsyncMock,
    ):
        """Test scheduling recurring execution with cron expression."""
        # Arrange
        mock_scheduler_command_port.schedule_recurring.return_value = {
            "schedule_id": "schedule-789",
            "cron_expression": "0 9 * * MON-FRI",
        }

        # Act
        response = client.post(
            "/api/v2/scheduler/schedule-recurring",
            json={
                "workflow_id": "workflow-123",
                "cron_expression": "0 9 * * MON-FRI",
                "description": "Weekday morning sync",
            },
        )

        # Assert
        assert response.status_code == status.HTTP_200_OK

    @pytest.mark.asyncio
    async def test_cancel_scheduled_execution(
        self,
        client: TestClient,
        mock_scheduler_command_port: AsyncMock,
    ):
        """Test cancelling a scheduled execution."""
        # Arrange
        mock_scheduler_command_port.cancel_schedule.return_value = {
            "success": True,
        }

        # Act
        response = client.delete("/api/v2/scheduler/schedule/schedule-123")

        # Assert
        assert response.status_code == status.HTTP_200_OK

    @pytest.mark.asyncio
    async def test_cancel_nonexistent_schedule(
        self,
        client: TestClient,
        mock_scheduler_command_port: AsyncMock,
    ):
        """Test cancelling non-existent schedule."""
        # Arrange
        mock_scheduler_command_port.cancel_schedule.side_effect = Exception(
            "Schedule not found"
        )

        # Act
        response = client.delete("/api/v2/scheduler/schedule/nonexistent")

        # Assert
        assert response.status_code == status.HTTP_404_NOT_FOUND


# ============================================================================
# Scheduled Task Retrieval Tests
# ============================================================================

class TestScheduledTaskRetrieval:
    """Tests for retrieving scheduled tasks."""

    @pytest.mark.asyncio
    async def test_get_scheduled_tasks_all(
        self,
        client: TestClient,
        mock_scheduler_query_port: AsyncMock,
    ):
        """Test retrieving all scheduled tasks."""
        # Arrange
        mock_scheduler_query_port.get_scheduled_tasks.return_value = {
            "tasks": [
                {
                    "schedule_id": "schedule-123",
                    "work_item_id": "work-item-123",
                    "execution_time": datetime.utcnow().isoformat(),
                },
                {
                    "schedule_id": "schedule-456",
                    "work_item_id": "work-item-456",
                    "execution_time": (datetime.utcnow() + timedelta(hours=1)).isoformat(),
                },
            ],
            "total": 2,
        }

        # Act
        response = client.get("/api/v2/scheduler/scheduled-tasks")

        # Assert
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert len(data["tasks"]) == 2

    @pytest.mark.asyncio
    async def test_get_scheduled_tasks_filtered_by_workflow(
        self,
        client: TestClient,
        mock_scheduler_query_port: AsyncMock,
    ):
        """Test retrieving scheduled tasks filtered by workflow."""
        # Arrange
        mock_scheduler_query_port.get_scheduled_tasks.return_value = {
            "tasks": [
                {
                    "schedule_id": "schedule-123",
                    "workflow_id": "workflow-123",
                }
            ],
            "total": 1,
        }

        # Act
        response = client.get("/api/v2/scheduler/scheduled-tasks?workflow_id=workflow-123")

        # Assert
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert len(data["tasks"]) == 1


# ============================================================================
# Execution Queue Tests
# ============================================================================

class TestExecutionQueue:
    """Tests for execution queue management."""

    @pytest.mark.asyncio
    async def test_get_execution_queue(
        self,
        client: TestClient,
        mock_scheduler_query_port: AsyncMock,
    ):
        """Test retrieving execution queue."""
        # Arrange
        mock_scheduler_query_port.get_execution_queue.return_value = {
            "queue": [
                {
                    "execution_id": "exec-123",
                    "work_item_id": "work-item-123",
                    "queued_at": datetime.utcnow().isoformat(),
                    "priority": "high",
                },
                {
                    "execution_id": "exec-456",
                    "work_item_id": "work-item-456",
                    "queued_at": datetime.utcnow().isoformat(),
                    "priority": "normal",
                },
            ],
            "total": 2,
        }

        # Act
        response = client.get("/api/v2/scheduler/execution-queue")

        # Assert
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert len(data["queue"]) == 2

    @pytest.mark.asyncio
    async def test_clear_execution_queue(
        self,
        client: TestClient,
        mock_scheduler_command_port: AsyncMock,
    ):
        """Test clearing the execution queue."""
        # Arrange
        mock_scheduler_command_port.clear_queue.return_value = {
            "success": True,
            "cleared_count": 5,
        }

        # Act
        response = client.post("/api/v2/scheduler/execution-queue/clear")

        # Assert
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["cleared_count"] == 5


# ============================================================================
# Schedule Configuration Tests
# ============================================================================

class TestScheduleConfiguration:
    """Tests for updating scheduler configuration."""

    @pytest.mark.asyncio
    async def test_update_schedule_configuration(
        self,
        client: TestClient,
        mock_scheduler_command_port: AsyncMock,
    ):
        """Test updating schedule configuration."""
        # Arrange
        mock_scheduler_command_port.update_configuration.return_value = {
            "success": True,
        }

        # Act
        response = client.put(
            "/api/v2/scheduler/config",
            json={
                "poll_interval_seconds": 60,
                "max_queue_size": 100,
            },
        )

        # Assert
        assert response.status_code == status.HTTP_200_OK

    @pytest.mark.asyncio
    async def test_get_schedule_configuration(
        self,
        client: TestClient,
        mock_scheduler_query_port: AsyncMock,
    ):
        """Test retrieving schedule configuration."""
        # Arrange
        mock_scheduler_query_port.get_configuration.return_value = {
            "poll_interval_seconds": 30,
            "max_queue_size": 50,
            "max_concurrent_executions": 5,
        }

        # Act
        response = client.get("/api/v2/scheduler/config")

        # Assert
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["poll_interval_seconds"] == 30


# ============================================================================
# Health Check Tests
# ============================================================================

class TestSchedulerHealth:
    """Tests for scheduler health checks."""

    @pytest.mark.asyncio
    async def test_health_check_healthy(
        self,
        client: TestClient,
        mock_scheduler_query_port: AsyncMock,
    ):
        """Test health check when scheduler is healthy."""
        # Arrange
        mock_scheduler_query_port.health_check.return_value = {
            "status": "healthy",
            "checks": {
                "database": "ok",
                "task_queue": "ok",
                "time_sync": "ok",
            },
        }

        # Act
        response = client.get("/api/v2/scheduler/health")

        # Assert
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["status"] == "healthy"

    @pytest.mark.asyncio
    async def test_health_check_degraded(
        self,
        client: TestClient,
        mock_scheduler_query_port: AsyncMock,
    ):
        """Test health check when scheduler is degraded."""
        # Arrange
        mock_scheduler_query_port.health_check.return_value = {
            "status": "degraded",
            "checks": {
                "database": "ok",
                "task_queue": "degraded",
                "time_sync": "ok",
            },
        }

        # Act
        response = client.get("/api/v2/scheduler/health")

        # Assert
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["status"] == "degraded"


# ============================================================================
# Error Handling Tests
# ============================================================================

class TestSchedulerErrorHandling:
    """Tests for scheduler error handling."""

    @pytest.mark.asyncio
    async def test_schedule_with_invalid_cron_expression(
        self,
        client: TestClient,
        mock_scheduler_command_port: AsyncMock,
    ):
        """Test scheduling with invalid cron expression."""
        # Arrange
        mock_scheduler_command_port.schedule_recurring.side_effect = ValueError(
            "Invalid cron expression"
        )

        # Act
        response = client.post(
            "/api/v2/scheduler/schedule-recurring",
            json={
                "workflow_id": "workflow-123",
                "cron_expression": "invalid-cron",
            },
        )

        # Assert
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    @pytest.mark.asyncio
    async def test_schedule_with_past_execution_time(
        self,
        client: TestClient,
        mock_scheduler_command_port: AsyncMock,
    ):
        """Test scheduling execution in the past."""
        # Arrange
        past_time = (datetime.utcnow() - timedelta(hours=1)).isoformat()
        mock_scheduler_command_port.schedule_execution.side_effect = ValueError(
            "Execution time must be in the future"
        )

        # Act
        response = client.post(
            "/api/v2/scheduler/schedule",
            json={
                "work_item_id": "work-item-123",
                "workflow_id": "workflow-123",
                "execute_at": past_time,
            },
        )

        # Assert
        assert response.status_code == status.HTTP_400_BAD_REQUEST
