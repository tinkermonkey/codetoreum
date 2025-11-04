"""
Integration tests for workflows REST API endpoints.

Tests workflow CRUD operations, stage management, execution, pause/resume,
versioning, and validation.
"""

import pytest
from datetime import datetime
from typing import AsyncGenerator
from unittest.mock import AsyncMock, MagicMock

from fastapi import FastAPI, status
from fastapi.testclient import TestClient

from codetoreum.adapters.primary.routers.workflows import create_workflows_router
from codetoreum.domain.models.workflow import Workflow, WorkflowStatus, PipelineStage
from codetoreum.ports.input.workflow_command import IWorkflowCommandPort
from codetoreum.ports.input.workflow_query import IWorkflowQueryPort


# ============================================================================
# Fixtures
# ============================================================================

@pytest.fixture
def mock_workflow_command_port() -> AsyncMock:
    """Create mock workflow command port for testing."""
    return AsyncMock(spec=IWorkflowCommandPort)


@pytest.fixture
def mock_workflow_query_port() -> AsyncMock:
    """Create mock workflow query port for testing."""
    return AsyncMock(spec=IWorkflowQueryPort)


@pytest.fixture
def test_app(
    mock_workflow_command_port: AsyncMock,
    mock_workflow_query_port: AsyncMock,
) -> FastAPI:
    """Create test FastAPI application with workflows router."""
    app = FastAPI()

    router = create_workflows_router(
        command_port=mock_workflow_command_port,
        query_port=mock_workflow_query_port,
        auth_deps=None,
    )

    app.include_router(router)
    return app


@pytest.fixture
def client(test_app: FastAPI) -> TestClient:
    """Create test client for making HTTP requests."""
    with TestClient(test_app) as test_client:
        yield test_client


@pytest.fixture
def sample_workflow() -> Workflow:
    """Create sample workflow for testing."""
    return Workflow(
        id="workflow-123",
        name="test-workflow",
        description="Test workflow",
        project_id="proj-123",
        version=1,
        status=WorkflowStatus.ACTIVE,
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
        stages=[
            PipelineStage(
                name="analysis",
                agent_id="agent-analyzer",
                entry_conditions={"requires_tests": False},
                order=0,
            ),
            PipelineStage(
                name="implementation",
                agent_id="agent-coder",
                entry_conditions={"requires_approval": True},
                order=1,
            ),
        ],
        metadata={"workflow_type": "ci"},
    )


# ============================================================================
# Workflow CRUD Tests
# ============================================================================

class TestWorkflowCRUD:
    """Tests for workflow creation, retrieval, update, and deletion."""

    @pytest.mark.asyncio
    async def test_create_workflow_with_stages(
        self,
        client: TestClient,
        mock_workflow_command_port: AsyncMock,
    ):
        """Test creating workflow with multiple stages."""
        # Arrange
        mock_workflow_command_port.create_workflow.return_value = {
            "workflow_id": "workflow-123",
            "status": "active",
        }

        # Act
        response = client.post(
            "/api/v2/workflows",
            json={
                "name": "test-workflow",
                "project_id": "proj-123",
                "description": "Test workflow",
                "stages": [
                    {
                        "name": "analysis",
                        "agent_id": "agent-analyzer",
                        "entry_conditions": {},
                    },
                    {
                        "name": "implementation",
                        "agent_id": "agent-coder",
                        "entry_conditions": {"requires_approval": True},
                    },
                ],
            },
        )

        # Assert
        assert response.status_code == status.HTTP_201_CREATED
        data = response.json()
        assert data["workflow_id"] == "workflow-123"

    @pytest.mark.asyncio
    async def test_create_workflow_validation_error(
        self,
        client: TestClient,
        mock_workflow_command_port: AsyncMock,
    ):
        """Test creating workflow with invalid data."""
        # Arrange
        mock_workflow_command_port.create_workflow.side_effect = ValueError(
            "Invalid workflow configuration"
        )

        # Act
        response = client.post(
            "/api/v2/workflows",
            json={
                "name": "",  # Invalid empty name
                "project_id": "proj-123",
                "stages": [],  # Invalid empty stages
            },
        )

        # Assert
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    @pytest.mark.asyncio
    async def test_get_workflow_details(
        self,
        client: TestClient,
        mock_workflow_query_port: AsyncMock,
        sample_workflow: Workflow,
    ):
        """Test retrieving workflow details."""
        # Arrange
        mock_workflow_query_port.get_workflow.return_value = sample_workflow

        # Act
        response = client.get("/api/v2/workflows/workflow-123")

        # Assert
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["id"] == "workflow-123"
        assert len(data["stages"]) == 2

    @pytest.mark.asyncio
    async def test_list_workflows_with_filtering(
        self,
        client: TestClient,
        mock_workflow_query_port: AsyncMock,
        sample_workflow: Workflow,
    ):
        """Test listing workflows with filters."""
        # Arrange
        mock_workflow_query_port.list_workflows.return_value = {
            "items": [sample_workflow],
            "total": 1,
        }

        # Act
        response = client.get("/api/v2/workflows?project_id=proj-123&status=active")

        # Assert
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert len(data["items"]) == 1

    @pytest.mark.asyncio
    async def test_update_workflow_configuration(
        self,
        client: TestClient,
        mock_workflow_command_port: AsyncMock,
    ):
        """Test updating workflow configuration."""
        # Arrange
        mock_workflow_command_port.update_workflow.return_value = {
            "success": True,
            "version": 2,
        }

        # Act
        response = client.put(
            "/api/v2/workflows/workflow-123",
            json={
                "description": "Updated workflow description",
                "metadata": {"priority": "high"},
            },
        )

        # Assert
        assert response.status_code == status.HTTP_200_OK

    @pytest.mark.asyncio
    async def test_delete_workflow(
        self,
        client: TestClient,
        mock_workflow_command_port: AsyncMock,
    ):
        """Test deleting workflow."""
        # Arrange
        mock_workflow_command_port.delete_workflow.return_value = {
            "success": True,
        }

        # Act
        response = client.delete("/api/v2/workflows/workflow-123")

        # Assert
        assert response.status_code == status.HTTP_200_OK


# ============================================================================
# Stage Management Tests
# ============================================================================

class TestStageManagement:
    """Tests for adding, updating, removing, and reordering stages."""

    @pytest.mark.asyncio
    async def test_add_stage_to_workflow(
        self,
        client: TestClient,
        mock_workflow_command_port: AsyncMock,
    ):
        """Test adding a new stage to workflow."""
        # Arrange
        mock_workflow_command_port.add_stage.return_value = {
            "success": True,
            "stage_name": "review",
        }

        # Act
        response = client.post(
            "/api/v2/workflows/workflow-123/stages",
            json={
                "name": "review",
                "agent_id": "agent-reviewer",
                "entry_conditions": {"requires_tests_passed": True},
                "insert_after": "implementation",
            },
        )

        # Assert
        assert response.status_code == status.HTTP_200_OK

    @pytest.mark.asyncio
    async def test_remove_stage_from_workflow(
        self,
        client: TestClient,
        mock_workflow_command_port: AsyncMock,
    ):
        """Test removing a stage from workflow."""
        # Arrange
        mock_workflow_command_port.remove_stage.return_value = {
            "success": True,
        }

        # Act
        response = client.delete("/api/v2/workflows/workflow-123/stages/analysis")

        # Assert
        assert response.status_code == status.HTTP_200_OK

    @pytest.mark.asyncio
    async def test_reorder_stages(
        self,
        client: TestClient,
        mock_workflow_command_port: AsyncMock,
    ):
        """Test reordering workflow stages."""
        # Arrange
        mock_workflow_command_port.reorder_stages.return_value = {
            "success": True,
        }

        # Act
        response = client.put(
            "/api/v2/workflows/workflow-123/stages/reorder",
            json={
                "stage_order": ["implementation", "analysis", "review"],
            },
        )

        # Assert
        assert response.status_code == status.HTTP_200_OK

    @pytest.mark.asyncio
    async def test_update_stage_configuration(
        self,
        client: TestClient,
        mock_workflow_command_port: AsyncMock,
    ):
        """Test updating stage configuration."""
        # Arrange
        mock_workflow_command_port.update_stage.return_value = {
            "success": True,
        }

        # Act
        response = client.put(
            "/api/v2/workflows/workflow-123/stages/analysis",
            json={
                "agent_id": "agent-analyzer-v2",
                "entry_conditions": {"min_confidence": 0.8},
            },
        )

        # Assert
        assert response.status_code == status.HTTP_200_OK


# ============================================================================
# Workflow Execution Tests
# ============================================================================

class TestWorkflowExecution:
    """Tests for workflow execution operations."""

    @pytest.mark.asyncio
    async def test_execute_workflow(
        self,
        client: TestClient,
        mock_workflow_command_port: AsyncMock,
    ):
        """Test executing a workflow."""
        # Arrange
        mock_workflow_command_port.execute_workflow.return_value = {
            "execution_id": "exec-123",
            "status": "running",
        }

        # Act
        response = client.post(
            "/api/v2/workflows/workflow-123/execute",
            json={
                "work_item_id": "work-item-123",
                "parameters": {"dry_run": False},
            },
        )

        # Assert
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["execution_id"] == "exec-123"

    @pytest.mark.asyncio
    async def test_pause_workflow(
        self,
        client: TestClient,
        mock_workflow_command_port: AsyncMock,
    ):
        """Test pausing workflow execution."""
        # Arrange
        mock_workflow_command_port.pause_workflow.return_value = {
            "success": True,
            "status": "paused",
        }

        # Act
        response = client.post("/api/v2/workflows/workflow-123/pause")

        # Assert
        assert response.status_code == status.HTTP_200_OK

    @pytest.mark.asyncio
    async def test_resume_workflow(
        self,
        client: TestClient,
        mock_workflow_command_port: AsyncMock,
    ):
        """Test resuming paused workflow."""
        # Arrange
        mock_workflow_command_port.resume_workflow.return_value = {
            "success": True,
            "status": "active",
        }

        # Act
        response = client.post("/api/v2/workflows/workflow-123/resume")

        # Assert
        assert response.status_code == status.HTTP_200_OK


# ============================================================================
# Workflow Validation Tests
# ============================================================================

class TestWorkflowValidation:
    """Tests for workflow configuration validation."""

    @pytest.mark.asyncio
    async def test_validate_workflow_configuration(
        self,
        client: TestClient,
        mock_workflow_command_port: AsyncMock,
    ):
        """Test validating workflow configuration."""
        # Arrange
        mock_workflow_command_port.validate_workflow.return_value = {
            "valid": True,
            "errors": [],
            "warnings": [],
        }

        # Act
        response = client.post(
            "/api/v2/workflows/validate",
            json={
                "name": "test-workflow",
                "stages": [
                    {"name": "analysis", "agent_id": "agent-analyzer"},
                ],
            },
        )

        # Assert
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["valid"] is True

    @pytest.mark.asyncio
    async def test_validate_workflow_with_errors(
        self,
        client: TestClient,
        mock_workflow_command_port: AsyncMock,
    ):
        """Test validating invalid workflow configuration."""
        # Arrange
        mock_workflow_command_port.validate_workflow.return_value = {
            "valid": False,
            "errors": [
                "Stage 'analysis' references non-existent agent",
                "Circular dependency detected",
            ],
            "warnings": ["No retry policy configured"],
        }

        # Act
        response = client.post(
            "/api/v2/workflows/validate",
            json={
                "name": "test-workflow",
                "stages": [
                    {"name": "analysis", "agent_id": "nonexistent-agent"},
                ],
            },
        )

        # Assert
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["valid"] is False
        assert len(data["errors"]) == 2


# ============================================================================
# Workflow Versioning Tests
# ============================================================================

class TestWorkflowVersioning:
    """Tests for workflow versioning."""

    @pytest.mark.asyncio
    async def test_get_workflow_version_history(
        self,
        client: TestClient,
        mock_workflow_query_port: AsyncMock,
    ):
        """Test retrieving workflow version history."""
        # Arrange
        mock_workflow_query_port.get_version_history.return_value = {
            "versions": [
                {"version": 2, "timestamp": datetime.utcnow().isoformat()},
                {"version": 1, "timestamp": datetime.utcnow().isoformat()},
            ],
            "total": 2,
        }

        # Act
        response = client.get("/api/v2/workflows/workflow-123/history")

        # Assert
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert len(data["versions"]) == 2

    @pytest.mark.asyncio
    async def test_rollback_to_previous_version(
        self,
        client: TestClient,
        mock_workflow_command_port: AsyncMock,
    ):
        """Test rolling back workflow to previous version."""
        # Arrange
        mock_workflow_command_port.rollback_to_version.return_value = {
            "success": True,
            "version": 3,
        }

        # Act
        response = client.post(
            "/api/v2/workflows/workflow-123/rollback",
            json={"target_version": 1},
        )

        # Assert
        assert response.status_code == status.HTTP_200_OK


# ============================================================================
# Concurrent Operations Tests
# ============================================================================

class TestConcurrentWorkflowOperations:
    """Tests for handling concurrent workflow operations."""

    @pytest.mark.asyncio
    async def test_concurrent_stage_modifications(
        self,
        client: TestClient,
        mock_workflow_command_port: AsyncMock,
    ):
        """Test handling concurrent stage modifications."""
        # Arrange
        mock_workflow_command_port.add_stage.side_effect = [
            {"success": True, "stage_name": "review"},
            Exception("Concurrent modification detected"),
        ]

        # Act
        response1 = client.post(
            "/api/v2/workflows/workflow-123/stages",
            json={"name": "review", "agent_id": "agent-reviewer"},
        )
        response2 = client.post(
            "/api/v2/workflows/workflow-123/stages",
            json={"name": "testing", "agent_id": "agent-tester"},
        )

        # Assert
        assert response1.status_code == status.HTTP_200_OK
        assert response2.status_code == status.HTTP_409_CONFLICT

    @pytest.mark.asyncio
    async def test_optimistic_locking_version_conflict(
        self,
        client: TestClient,
        mock_workflow_command_port: AsyncMock,
    ):
        """Test handling version conflict with optimistic locking."""
        # Arrange
        mock_workflow_command_port.update_workflow.side_effect = Exception(
            "Version conflict"
        )

        # Act
        response = client.put(
            "/api/v2/workflows/workflow-123",
            json={
                "description": "Update",
                "expected_version": 1,
            },
        )

        # Assert
        assert response.status_code == status.HTTP_409_CONFLICT
