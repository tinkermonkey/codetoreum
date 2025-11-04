"""
Integration tests for orchestrator REST API endpoints.

Tests orchestrator lifecycle, work item processing, retry logic, queue management,
configuration reload, and health checks.
"""

import pytest
from datetime import datetime
from typing import AsyncGenerator
from unittest.mock import AsyncMock, MagicMock

from fastapi import FastAPI, status
from fastapi.testclient import TestClient

from codetoreum.adapters.primary.routers.orchestrator import create_orchestrator_router
from codetoreum.ports.input.orchestrator_command import IOrchestratorCommandPort
from codetoreum.ports.input.orchestrator_query import IOrchestratorQueryPort


# ============================================================================
# Fixtures
# ============================================================================

@pytest.fixture
def mock_orchestrator_command_port() -> AsyncMock:
    """Create mock orchestrator command port for testing."""
    return AsyncMock(spec=IOrchestratorCommandPort)


@pytest.fixture
def mock_orchestrator_query_port() -> AsyncMock:
    """Create mock orchestrator query port for testing."""
    return AsyncMock(spec=IOrchestratorQueryPort)


@pytest.fixture
def test_app(
    mock_orchestrator_command_port: AsyncMock,
    mock_orchestrator_query_port: AsyncMock,
) -> FastAPI:
    """Create test FastAPI application with orchestrator router."""
    app = FastAPI()

    router = create_orchestrator_router(
        command_port=mock_orchestrator_command_port,
        query_port=mock_orchestrator_query_port,
        auth_deps=None,
    )

    app.include_router(router)
    return app


@pytest.fixture
def client(test_app: FastAPI) -> TestClient:
    """Create test client for making HTTP requests."""
    return TestClient(test_app)


# ============================================================================
# Orchestrator Lifecycle Tests
# ============================================================================

class TestOrchestratorLifecycle:
    """Tests for orchestrator start, stop, and status."""

    @pytest.mark.asyncio
    async def test_start_orchestrator(
        self,
        client: TestClient,
        mock_orchestrator_command_port: AsyncMock,
    ):
        """Test starting the orchestrator."""
        # Arrange
        mock_orchestrator_command_port.start.return_value = {
            "status": "running",
            "started_at": datetime.utcnow().isoformat(),
        }

        # Act
        response = client.post("/api/v2/orchestrator/start")

        # Assert
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["status"] == "running"

    @pytest.mark.asyncio
    async def test_start_orchestrator_already_running(
        self,
        client: TestClient,
        mock_orchestrator_command_port: AsyncMock,
    ):
        """Test starting orchestrator when already running."""
        # Arrange
        mock_orchestrator_command_port.start.side_effect = Exception(
            "Orchestrator is already running"
        )

        # Act
        response = client.post("/api/v2/orchestrator/start")

        # Assert
        assert response.status_code == status.HTTP_409_CONFLICT

    @pytest.mark.asyncio
    async def test_stop_orchestrator(
        self,
        client: TestClient,
        mock_orchestrator_command_port: AsyncMock,
    ):
        """Test stopping the orchestrator."""
        # Arrange
        mock_orchestrator_command_port.stop.return_value = {
            "status": "stopped",
            "stopped_at": datetime.utcnow().isoformat(),
        }

        # Act
        response = client.post("/api/v2/orchestrator/stop")

        # Assert
        assert response.status_code == status.HTTP_200_OK

    @pytest.mark.asyncio
    async def test_get_orchestrator_status(
        self,
        client: TestClient,
        mock_orchestrator_query_port: AsyncMock,
    ):
        """Test retrieving orchestrator status."""
        # Arrange
        mock_orchestrator_query_port.get_status.return_value = {
            "status": "running",
            "active_workflows": 3,
            "pending_work_items": 7,
            "uptime_seconds": 3600,
        }

        # Act
        response = client.get("/api/v2/orchestrator/status")

        # Assert
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["status"] == "running"
        assert data["active_workflows"] == 3

    @pytest.mark.asyncio
    async def test_pause_orchestrator(
        self,
        client: TestClient,
        mock_orchestrator_command_port: AsyncMock,
    ):
        """Test pausing the orchestrator."""
        # Arrange
        mock_orchestrator_command_port.pause.return_value = {
            "status": "paused",
        }

        # Act
        response = client.post("/api/v2/orchestrator/pause")

        # Assert
        assert response.status_code == status.HTTP_200_OK

    @pytest.mark.asyncio
    async def test_resume_orchestrator(
        self,
        client: TestClient,
        mock_orchestrator_command_port: AsyncMock,
    ):
        """Test resuming the orchestrator."""
        # Arrange
        mock_orchestrator_command_port.resume.return_value = {
            "status": "running",
        }

        # Act
        response = client.post("/api/v2/orchestrator/resume")

        # Assert
        assert response.status_code == status.HTTP_200_OK


# ============================================================================
# Work Item Processing Tests
# ============================================================================

class TestWorkItemProcessing:
    """Tests for processing work items through orchestrator."""

    @pytest.mark.asyncio
    async def test_process_work_item(
        self,
        client: TestClient,
        mock_orchestrator_command_port: AsyncMock,
    ):
        """Test processing a work item."""
        # Arrange
        mock_orchestrator_command_port.process_work_item.return_value = {
            "work_item_id": "work-item-123",
            "execution_id": "exec-123",
            "status": "processing",
        }

        # Act
        response = client.post(
            "/api/v2/orchestrator/process",
            json={
                "work_item_id": "work-item-123",
                "workflow_id": "workflow-123",
                "priority": "high",
            },
        )

        # Assert
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["work_item_id"] == "work-item-123"

    @pytest.mark.asyncio
    async def test_process_work_item_already_processing(
        self,
        client: TestClient,
        mock_orchestrator_command_port: AsyncMock,
    ):
        """Test processing work item that's already being processed."""
        # Arrange
        mock_orchestrator_command_port.process_work_item.side_effect = Exception(
            "Work item is already being processed"
        )

        # Act
        response = client.post(
            "/api/v2/orchestrator/process",
            json={"work_item_id": "work-item-123"},
        )

        # Assert
        assert response.status_code == status.HTTP_409_CONFLICT

    @pytest.mark.asyncio
    async def test_retry_failed_execution(
        self,
        client: TestClient,
        mock_orchestrator_command_port: AsyncMock,
    ):
        """Test retrying a failed execution."""
        # Arrange
        mock_orchestrator_command_port.retry_execution.return_value = {
            "original_execution_id": "exec-123",
            "new_execution_id": "exec-456",
            "status": "retrying",
        }

        # Act
        response = client.post(
            "/api/v2/orchestrator/retry",
            json={
                "execution_id": "exec-123",
                "retry_from_stage": "implementation",
            },
        )

        # Assert
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["new_execution_id"] == "exec-456"


# ============================================================================
# Queue Management Tests
# ============================================================================

class TestQueueManagement:
    """Tests for orchestrator queue management."""

    @pytest.mark.asyncio
    async def test_get_active_workflows(
        self,
        client: TestClient,
        mock_orchestrator_query_port: AsyncMock,
    ):
        """Test retrieving active workflows."""
        # Arrange
        mock_orchestrator_query_port.get_active_workflows.return_value = {
            "workflows": [
                {
                    "workflow_id": "workflow-123",
                    "work_item_id": "work-item-123",
                    "current_stage": "implementation",
                    "started_at": datetime.utcnow().isoformat(),
                }
            ],
            "total": 1,
        }

        # Act
        response = client.get("/api/v2/orchestrator/active-workflows")

        # Assert
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert len(data["workflows"]) == 1

    @pytest.mark.asyncio
    async def test_get_pending_queue(
        self,
        client: TestClient,
        mock_orchestrator_query_port: AsyncMock,
    ):
        """Test retrieving pending work items queue."""
        # Arrange
        mock_orchestrator_query_port.get_pending_queue.return_value = {
            "queue": [
                {
                    "work_item_id": "work-item-456",
                    "priority": "high",
                    "queued_at": datetime.utcnow().isoformat(),
                },
                {
                    "work_item_id": "work-item-789",
                    "priority": "normal",
                    "queued_at": datetime.utcnow().isoformat(),
                },
            ],
            "total": 2,
        }

        # Act
        response = client.get("/api/v2/orchestrator/pending-queue")

        # Assert
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert len(data["queue"]) == 2


# ============================================================================
# Configuration Management Tests
# ============================================================================

class TestOrchestratorConfiguration:
    """Tests for orchestrator configuration management."""

    @pytest.mark.asyncio
    async def test_reload_configuration(
        self,
        client: TestClient,
        mock_orchestrator_command_port: AsyncMock,
    ):
        """Test reloading orchestrator configuration."""
        # Arrange
        mock_orchestrator_command_port.reload_configuration.return_value = {
            "success": True,
            "reloaded_at": datetime.utcnow().isoformat(),
        }

        # Act
        response = client.post("/api/v2/orchestrator/reload-config")

        # Assert
        assert response.status_code == status.HTTP_200_OK

    @pytest.mark.asyncio
    async def test_get_configuration(
        self,
        client: TestClient,
        mock_orchestrator_query_port: AsyncMock,
    ):
        """Test retrieving orchestrator configuration."""
        # Arrange
        mock_orchestrator_query_port.get_configuration.return_value = {
            "max_concurrent_workflows": 5,
            "queue_check_interval_seconds": 30,
            "retry_policy": {"max_attempts": 3, "backoff_multiplier": 2},
        }

        # Act
        response = client.get("/api/v2/orchestrator/config")

        # Assert
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["max_concurrent_workflows"] == 5


# ============================================================================
# Health Check Tests
# ============================================================================

class TestOrchestratorHealth:
    """Tests for orchestrator health checks."""

    @pytest.mark.asyncio
    async def test_health_check_healthy(
        self,
        client: TestClient,
        mock_orchestrator_query_port: AsyncMock,
    ):
        """Test health check when orchestrator is healthy."""
        # Arrange
        mock_orchestrator_query_port.health_check.return_value = {
            "status": "healthy",
            "checks": {
                "database": "ok",
                "event_store": "ok",
                "task_queue": "ok",
            },
        }

        # Act
        response = client.get("/api/v2/orchestrator/health")

        # Assert
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["status"] == "healthy"

    @pytest.mark.asyncio
    async def test_health_check_degraded(
        self,
        client: TestClient,
        mock_orchestrator_query_port: AsyncMock,
    ):
        """Test health check when orchestrator is degraded."""
        # Arrange
        mock_orchestrator_query_port.health_check.return_value = {
            "status": "degraded",
            "checks": {
                "database": "ok",
                "event_store": "degraded",
                "task_queue": "ok",
            },
        }

        # Act
        response = client.get("/api/v2/orchestrator/health")

        # Assert
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["status"] == "degraded"


# ============================================================================
# Error Handling Tests
# ============================================================================

class TestOrchestratorErrorHandling:
    """Tests for orchestrator error handling."""

    @pytest.mark.asyncio
    async def test_process_work_item_with_invalid_workflow(
        self,
        client: TestClient,
        mock_orchestrator_command_port: AsyncMock,
    ):
        """Test processing work item with invalid workflow."""
        # Arrange
        mock_orchestrator_command_port.process_work_item.side_effect = Exception(
            "Workflow not found"
        )

        # Act
        response = client.post(
            "/api/v2/orchestrator/process",
            json={
                "work_item_id": "work-item-123",
                "workflow_id": "nonexistent",
            },
        )

        # Assert
        assert response.status_code == status.HTTP_404_NOT_FOUND

    @pytest.mark.asyncio
    async def test_retry_nonexistent_execution(
        self,
        client: TestClient,
        mock_orchestrator_command_port: AsyncMock,
    ):
        """Test retrying non-existent execution."""
        # Arrange
        mock_orchestrator_command_port.retry_execution.side_effect = Exception(
            "Execution not found"
        )

        # Act
        response = client.post(
            "/api/v2/orchestrator/retry",
            json={"execution_id": "nonexistent"},
        )

        # Assert
        assert response.status_code == status.HTTP_404_NOT_FOUND
