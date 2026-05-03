"""Integration tests for board workflow template REST API endpoints.

Tests all board workflow template CRUD endpoints including:
- Authorization checks (cross-project access validation)
- Input validation
- Error handling (without exposing internal details)
- Unique template ID generation
"""

from collections.abc import Generator
from datetime import UTC, datetime
from unittest.mock import AsyncMock

import pytest
from fastapi import FastAPI, status
from fastapi.testclient import TestClient

from codetoreum.adapters.primary.routers.board_workflow_templates import (
    BoardWorkflowTemplateResponse,
    create_board_workflow_router,
)
from codetoreum.domain.board_workflow_template import (
    BoardWorkflowTemplate,
    ColumnTemplate,
    ColumnType,
)
from codetoreum.ports.output.workflow_config_service import IWorkflowConfigService


# ============================================================================
# Fixtures
# ============================================================================


@pytest.fixture
def mock_workflow_config_service() -> AsyncMock:
    """Create mock workflow config service for testing."""
    return AsyncMock(spec=IWorkflowConfigService)


@pytest.fixture
def test_app(mock_workflow_config_service: AsyncMock) -> FastAPI:
    """Create test FastAPI application with board workflow template router."""
    app = FastAPI()

    # Create router without authentication for testing
    router = create_board_workflow_router(
        workflow_config_service=mock_workflow_config_service,
        auth_deps=None,
    )

    app.include_router(router)
    return app


@pytest.fixture
def client(test_app: FastAPI) -> Generator[TestClient, None, None]:
    """Create test client for making HTTP requests."""
    with TestClient(test_app) as test_client:
        yield test_client


@pytest.fixture
def sample_template() -> BoardWorkflowTemplate:
    """Create sample board workflow template for testing."""
    columns = (
        ColumnTemplate(
            name="Backlog",
            type=ColumnType.MANUAL,
            agent_id=None,
            is_pipeline_trigger=False,
            is_exit_column=False,
            position=0,
            auto_progress_on_completion=False,
            sla_seconds=None,
            on_failure_column=None,
            sla_escalation_column=None,
            execution_type="task_queue",
        ),
        ColumnTemplate(
            name="In Progress",
            type=ColumnType.AUTOMATED,
            agent_id="agent-coder",
            is_pipeline_trigger=True,
            is_exit_column=False,
            position=1,
            auto_progress_on_completion=False,
            sla_seconds=3600,
            on_failure_column="Backlog",
            sla_escalation_column="Review",
            execution_type="task_queue",
        ),
        ColumnTemplate(
            name="Review",
            type=ColumnType.MANUAL,
            agent_id=None,
            is_pipeline_trigger=False,
            is_exit_column=False,
            position=2,
            auto_progress_on_completion=False,
            sla_seconds=1800,
            on_failure_column=None,
            sla_escalation_column=None,
            execution_type="task_queue",
        ),
        ColumnTemplate(
            name="Done",
            type=ColumnType.MANUAL,
            agent_id=None,
            is_pipeline_trigger=False,
            is_exit_column=True,
            position=3,
            auto_progress_on_completion=False,
            sla_seconds=None,
            on_failure_column=None,
            sla_escalation_column=None,
            execution_type="task_queue",
        ),
    )

    return BoardWorkflowTemplate(
        id="template-123",
        name="Standard SDLC Workflow",
        board_id="board-001",
        project_id="proj-123",
        columns=columns,
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )


# ============================================================================
# List Templates Tests
# ============================================================================


class TestListTemplates:
    """Tests for listing board workflow templates."""

    @pytest.mark.asyncio
    async def test_list_templates_success(
        self,
        client: TestClient,
        mock_workflow_config_service: AsyncMock,
        sample_template: BoardWorkflowTemplate,
    ):
        """Test successfully listing templates for a project."""
        # Arrange
        mock_workflow_config_service.list_board_workflow_templates.return_value = [
            sample_template
        ]

        # Act
        response = client.get("/api/v2/projects/proj-123/board-workflows")

        # Assert
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["total_count"] == 1
        assert len(data["templates"]) == 1
        assert data["templates"][0]["id"] == "template-123"
        assert data["templates"][0]["name"] == "Standard SDLC Workflow"
        assert data["templates"][0]["project_id"] == "proj-123"
        assert len(data["templates"][0]["columns"]) == 4
        mock_workflow_config_service.list_board_workflow_templates.assert_called_once_with(
            "proj-123"
        )

    @pytest.mark.asyncio
    async def test_list_templates_empty(
        self,
        client: TestClient,
        mock_workflow_config_service: AsyncMock,
    ):
        """Test listing templates when no templates exist for a project."""
        # Arrange
        mock_workflow_config_service.list_board_workflow_templates.return_value = []

        # Act
        response = client.get("/api/v2/projects/proj-123/board-workflows")

        # Assert
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["total_count"] == 0
        assert len(data["templates"]) == 0

    @pytest.mark.asyncio
    async def test_list_templates_internal_error_no_details(
        self,
        client: TestClient,
        mock_workflow_config_service: AsyncMock,
    ):
        """Test that internal error details are not exposed in error response."""
        # Arrange
        mock_workflow_config_service.list_board_workflow_templates.side_effect = Exception(
            "Elasticsearch connection failed: host=10.0.0.5:9200 credentials=admin:password"
        )

        # Act
        response = client.get("/api/v2/projects/proj-123/board-workflows")

        # Assert
        assert response.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
        data = response.json()
        # Ensure no internal details are leaked
        assert "Elasticsearch" not in data["detail"]
        assert "10.0.0.5" not in data["detail"]
        assert "password" not in data["detail"]
        assert data["detail"] == "Failed to list templates"


# ============================================================================
# Get Template Tests
# ============================================================================


class TestGetTemplate:
    """Tests for retrieving a specific board workflow template."""

    @pytest.mark.asyncio
    async def test_get_template_success(
        self,
        client: TestClient,
        mock_workflow_config_service: AsyncMock,
        sample_template: BoardWorkflowTemplate,
    ):
        """Test successfully retrieving a template."""
        # Arrange
        mock_workflow_config_service.get_board_workflow_template.return_value = (
            sample_template
        )

        # Act
        response = client.get(
            "/api/v2/projects/proj-123/board-workflows/board-001"
        )

        # Assert
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["id"] == "template-123"
        assert data["board_id"] == "board-001"
        assert data["project_id"] == "proj-123"
        assert len(data["columns"]) == 4
        mock_workflow_config_service.get_board_workflow_template.assert_called_once_with(
            "board-001"
        )

    @pytest.mark.asyncio
    async def test_get_template_not_found(
        self,
        client: TestClient,
        mock_workflow_config_service: AsyncMock,
    ):
        """Test retrieving non-existent template returns 404."""
        # Arrange
        mock_workflow_config_service.get_board_workflow_template.return_value = None

        # Act
        response = client.get(
            "/api/v2/projects/proj-123/board-workflows/nonexistent"
        )

        # Assert
        assert response.status_code == status.HTTP_404_NOT_FOUND
        data = response.json()
        assert "not found" in data["detail"].lower()

    @pytest.mark.asyncio
    async def test_get_template_cross_project_access_denied(
        self,
        client: TestClient,
        mock_workflow_config_service: AsyncMock,
    ):
        """Test that templates from other projects cannot be accessed."""
        # Arrange
        other_project_template = BoardWorkflowTemplate(
            id="template-456",
            name="Other Project Template",
            board_id="board-002",
            project_id="proj-999",  # Different project
            columns=(ColumnTemplate(
                name="Todo",
                type=ColumnType.MANUAL,
                agent_id=None,
                is_pipeline_trigger=False,
                is_exit_column=False,
                position=0,
                auto_progress_on_completion=False,
                sla_seconds=None,
                on_failure_column=None,
                sla_escalation_column=None,
                execution_type="task_queue",
            ),),
        )
        mock_workflow_config_service.get_board_workflow_template.return_value = (
            other_project_template
        )

        # Act
        response = client.get(
            "/api/v2/projects/proj-123/board-workflows/board-002"
        )

        # Assert
        assert response.status_code == status.HTTP_404_NOT_FOUND
        data = response.json()
        assert "not found" in data["detail"].lower()

    @pytest.mark.asyncio
    async def test_get_template_internal_error_no_details(
        self,
        client: TestClient,
        mock_workflow_config_service: AsyncMock,
    ):
        """Test that internal error details are not exposed when getting template."""
        # Arrange
        mock_workflow_config_service.get_board_workflow_template.side_effect = (
            Exception("Index 'workflows' not found on cluster")
        )

        # Act
        response = client.get(
            "/api/v2/projects/proj-123/board-workflows/board-001"
        )

        # Assert
        assert response.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
        data = response.json()
        assert "workflows" not in data["detail"]
        assert data["detail"] == "Failed to get template"


# ============================================================================
# Create Template Tests
# ============================================================================


class TestCreateTemplate:
    """Tests for creating a new board workflow template."""

    @pytest.mark.asyncio
    async def test_create_template_success(
        self,
        client: TestClient,
        mock_workflow_config_service: AsyncMock,
    ):
        """Test successfully creating a new template."""
        # Arrange
        request_payload = {
            "name": "New Workflow",
            "columns": [
                {
                    "name": "Todo",
                    "type": "manual",
                    "agent_id": None,
                    "is_pipeline_trigger": False,
                    "is_exit_column": False,
                    "position": 0,
                    "auto_progress_on_completion": False,
                    "sla_seconds": None,
                    "on_failure_column": None,
                    "sla_escalation_column": None,
                    "execution_type": "task_queue",
                },
                {
                    "name": "Done",
                    "type": "manual",
                    "agent_id": None,
                    "is_pipeline_trigger": False,
                    "is_exit_column": True,
                    "position": 1,
                    "auto_progress_on_completion": False,
                    "sla_seconds": None,
                    "on_failure_column": None,
                    "sla_escalation_column": None,
                    "execution_type": "task_queue",
                },
            ],
        }

        # Mock should capture the template being saved
        async def capture_and_return(template: BoardWorkflowTemplate):
            return None

        mock_workflow_config_service.save_board_workflow_template.side_effect = (
            capture_and_return
        )

        # Act
        response = client.post(
            "/api/v2/projects/proj-123/board-workflows",
            json=request_payload,
        )

        # Assert
        assert response.status_code == status.HTTP_201_CREATED
        data = response.json()
        assert data["name"] == "New Workflow"
        assert data["project_id"] == "proj-123"
        assert len(data["columns"]) == 2
        assert data["columns"][0]["name"] == "Todo"
        assert data["columns"][1]["name"] == "Done"
        # Verify template ID was generated (should start with "template-")
        assert data["id"].startswith("template-")
        mock_workflow_config_service.save_board_workflow_template.assert_called_once()

    @pytest.mark.asyncio
    async def test_create_template_unique_ids(
        self,
        client: TestClient,
        mock_workflow_config_service: AsyncMock,
    ):
        """Test that multiple template creations generate unique IDs."""
        # Arrange
        request_payload = {
            "name": "Workflow",
            "columns": [
                {
                    "name": "Todo",
                    "type": "manual",
                    "agent_id": None,
                    "is_pipeline_trigger": False,
                    "is_exit_column": False,
                    "position": 0,
                    "auto_progress_on_completion": False,
                    "sla_seconds": None,
                    "on_failure_column": None,
                    "sla_escalation_column": None,
                    "execution_type": "task_queue",
                },
            ],
        }

        mock_workflow_config_service.save_board_workflow_template.return_value = None

        # Act - Create first template
        response1 = client.post(
            "/api/v2/projects/proj-123/board-workflows",
            json=request_payload,
        )
        first_id = response1.json()["id"]

        # Act - Create second template with same request
        response2 = client.post(
            "/api/v2/projects/proj-123/board-workflows",
            json=request_payload,
        )
        second_id = response2.json()["id"]

        # Assert - IDs should be different
        assert first_id != second_id
        assert first_id.startswith("template-")
        assert second_id.startswith("template-")

    @pytest.mark.asyncio
    async def test_create_template_invalid_column_type(
        self,
        client: TestClient,
        mock_workflow_config_service: AsyncMock,
    ):
        """Test creating template with invalid column type."""
        # Arrange
        request_payload = {
            "name": "New Workflow",
            "columns": [
                {
                    "name": "Todo",
                    "type": "invalid_type",  # Invalid type
                    "agent_id": None,
                    "is_pipeline_trigger": False,
                    "is_exit_column": False,
                    "position": 0,
                    "auto_progress_on_completion": False,
                    "sla_seconds": None,
                    "on_failure_column": None,
                    "sla_escalation_column": None,
                    "execution_type": "task_queue",
                },
            ],
        }

        # Act
        response = client.post(
            "/api/v2/projects/proj-123/board-workflows",
            json=request_payload,
        )

        # Assert
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    @pytest.mark.asyncio
    async def test_create_template_internal_error_no_details(
        self,
        client: TestClient,
        mock_workflow_config_service: AsyncMock,
    ):
        """Test that internal error details are not exposed when creating template."""
        # Arrange
        request_payload = {
            "name": "New Workflow",
            "columns": [
                {
                    "name": "Todo",
                    "type": "manual",
                    "agent_id": None,
                    "is_pipeline_trigger": False,
                    "is_exit_column": False,
                    "position": 0,
                    "auto_progress_on_completion": False,
                    "sla_seconds": None,
                    "on_failure_column": None,
                    "sla_escalation_column": None,
                    "execution_type": "task_queue",
                },
            ],
        }

        mock_workflow_config_service.save_board_workflow_template.side_effect = (
            Exception("Failed to write to Redis: timeout on key 'template:proj-123'")
        )

        # Act
        response = client.post(
            "/api/v2/projects/proj-123/board-workflows",
            json=request_payload,
        )

        # Assert
        assert response.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
        data = response.json()
        assert "Redis" not in data["detail"]
        assert "template:proj-123" not in data["detail"]
        assert data["detail"] == "Failed to create template"


# ============================================================================
# Update Template Tests
# ============================================================================


class TestUpdateTemplate:
    """Tests for updating an existing board workflow template."""

    @pytest.mark.asyncio
    async def test_update_template_success(
        self,
        client: TestClient,
        mock_workflow_config_service: AsyncMock,
        sample_template: BoardWorkflowTemplate,
    ):
        """Test successfully updating a template."""
        # Arrange
        mock_workflow_config_service.get_board_workflow_template.return_value = (
            sample_template
        )
        mock_workflow_config_service.save_board_workflow_template.return_value = None

        request_payload = {
            "name": "Updated SDLC Workflow",
            "columns": [
                {
                    "name": "Backlog",
                    "type": "manual",
                    "agent_id": None,
                    "is_pipeline_trigger": False,
                    "is_exit_column": False,
                    "position": 0,
                    "auto_progress_on_completion": False,
                    "sla_seconds": None,
                    "on_failure_column": None,
                    "sla_escalation_column": None,
                    "execution_type": "task_queue",
                },
                {
                    "name": "Done",
                    "type": "manual",
                    "agent_id": None,
                    "is_pipeline_trigger": False,
                    "is_exit_column": True,
                    "position": 1,
                    "auto_progress_on_completion": False,
                    "sla_seconds": None,
                    "on_failure_column": None,
                    "sla_escalation_column": None,
                    "execution_type": "task_queue",
                },
            ],
        }

        # Act
        response = client.put(
            "/api/v2/projects/proj-123/board-workflows/board-001",
            json=request_payload,
        )

        # Assert
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["name"] == "Updated SDLC Workflow"
        assert len(data["columns"]) == 2
        mock_workflow_config_service.save_board_workflow_template.assert_called_once()

    @pytest.mark.asyncio
    async def test_update_template_not_found(
        self,
        client: TestClient,
        mock_workflow_config_service: AsyncMock,
    ):
        """Test updating non-existent template returns 404."""
        # Arrange
        mock_workflow_config_service.get_board_workflow_template.return_value = None

        request_payload = {
            "name": "Updated Workflow",
            "columns": [
                {
                    "name": "Todo",
                    "type": "manual",
                    "agent_id": None,
                    "is_pipeline_trigger": False,
                    "is_exit_column": False,
                    "position": 0,
                    "auto_progress_on_completion": False,
                    "sla_seconds": None,
                    "on_failure_column": None,
                    "sla_escalation_column": None,
                    "execution_type": "task_queue",
                },
            ],
        }

        # Act
        response = client.put(
            "/api/v2/projects/proj-123/board-workflows/nonexistent",
            json=request_payload,
        )

        # Assert
        assert response.status_code == status.HTTP_404_NOT_FOUND

    @pytest.mark.asyncio
    async def test_update_template_cross_project_access_denied(
        self,
        client: TestClient,
        mock_workflow_config_service: AsyncMock,
    ):
        """Test that templates from other projects cannot be updated."""
        # Arrange
        other_project_template = BoardWorkflowTemplate(
            id="template-456",
            name="Other Project Template",
            board_id="board-002",
            project_id="proj-999",
            columns=(ColumnTemplate(
                name="Todo",
                type=ColumnType.MANUAL,
                agent_id=None,
                is_pipeline_trigger=False,
                is_exit_column=False,
                position=0,
                auto_progress_on_completion=False,
                sla_seconds=None,
                on_failure_column=None,
                sla_escalation_column=None,
                execution_type="task_queue",
            ),),
        )
        mock_workflow_config_service.get_board_workflow_template.return_value = (
            other_project_template
        )

        request_payload = {
            "name": "Updated Workflow",
            "columns": [
                {
                    "name": "Todo",
                    "type": "manual",
                    "agent_id": None,
                    "is_pipeline_trigger": False,
                    "is_exit_column": False,
                    "position": 0,
                    "auto_progress_on_completion": False,
                    "sla_seconds": None,
                    "on_failure_column": None,
                    "sla_escalation_column": None,
                    "execution_type": "task_queue",
                },
            ],
        }

        # Act
        response = client.put(
            "/api/v2/projects/proj-123/board-workflows/board-002",
            json=request_payload,
        )

        # Assert
        assert response.status_code == status.HTTP_404_NOT_FOUND

    @pytest.mark.asyncio
    async def test_update_template_internal_error_no_details(
        self,
        client: TestClient,
        mock_workflow_config_service: AsyncMock,
        sample_template: BoardWorkflowTemplate,
    ):
        """Test that internal error details are not exposed when updating template."""
        # Arrange
        mock_workflow_config_service.get_board_workflow_template.return_value = (
            sample_template
        )
        mock_workflow_config_service.save_board_workflow_template.side_effect = (
            Exception("Connection lost to database host 192.168.1.10:5432")
        )

        request_payload = {
            "name": "Updated Workflow",
            "columns": [
                {
                    "name": "Todo",
                    "type": "manual",
                    "agent_id": None,
                    "is_pipeline_trigger": False,
                    "is_exit_column": False,
                    "position": 0,
                    "auto_progress_on_completion": False,
                    "sla_seconds": None,
                    "on_failure_column": None,
                    "sla_escalation_column": None,
                    "execution_type": "task_queue",
                },
            ],
        }

        # Act
        response = client.put(
            "/api/v2/projects/proj-123/board-workflows/board-001",
            json=request_payload,
        )

        # Assert
        assert response.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
        data = response.json()
        assert "192.168.1.10" not in data["detail"]
        assert "5432" not in data["detail"]
        assert data["detail"] == "Failed to update template"


# ============================================================================
# Delete Template Tests
# ============================================================================


class TestDeleteTemplate:
    """Tests for deleting a board workflow template."""

    @pytest.mark.asyncio
    async def test_delete_template_success(
        self,
        client: TestClient,
        mock_workflow_config_service: AsyncMock,
        sample_template: BoardWorkflowTemplate,
    ):
        """Test successfully deleting a template."""
        # Arrange
        mock_workflow_config_service.get_board_workflow_template.return_value = (
            sample_template
        )
        mock_workflow_config_service.delete_board_workflow_template.return_value = None

        # Act
        response = client.delete(
            "/api/v2/projects/proj-123/board-workflows/board-001"
        )

        # Assert
        assert response.status_code == status.HTTP_204_NO_CONTENT
        mock_workflow_config_service.delete_board_workflow_template.assert_called_once_with(
            "board-001"
        )

    @pytest.mark.asyncio
    async def test_delete_template_not_found(
        self,
        client: TestClient,
        mock_workflow_config_service: AsyncMock,
    ):
        """Test deleting non-existent template returns 404."""
        # Arrange
        mock_workflow_config_service.get_board_workflow_template.return_value = None

        # Act
        response = client.delete(
            "/api/v2/projects/proj-123/board-workflows/nonexistent"
        )

        # Assert
        assert response.status_code == status.HTTP_404_NOT_FOUND

    @pytest.mark.asyncio
    async def test_delete_template_cross_project_access_denied(
        self,
        client: TestClient,
        mock_workflow_config_service: AsyncMock,
    ):
        """Test that templates from other projects cannot be deleted."""
        # Arrange
        other_project_template = BoardWorkflowTemplate(
            id="template-456",
            name="Other Project Template",
            board_id="board-002",
            project_id="proj-999",
            columns=(ColumnTemplate(
                name="Todo",
                type=ColumnType.MANUAL,
                agent_id=None,
                is_pipeline_trigger=False,
                is_exit_column=False,
                position=0,
                auto_progress_on_completion=False,
                sla_seconds=None,
                on_failure_column=None,
                sla_escalation_column=None,
                execution_type="task_queue",
            ),),
        )
        mock_workflow_config_service.get_board_workflow_template.return_value = (
            other_project_template
        )

        # Act
        response = client.delete(
            "/api/v2/projects/proj-123/board-workflows/board-002"
        )

        # Assert
        assert response.status_code == status.HTTP_404_NOT_FOUND
        # Verify delete was NOT called
        mock_workflow_config_service.delete_board_workflow_template.assert_not_called()

    @pytest.mark.asyncio
    async def test_delete_template_internal_error_no_details(
        self,
        client: TestClient,
        mock_workflow_config_service: AsyncMock,
        sample_template: BoardWorkflowTemplate,
    ):
        """Test that internal error details are not exposed when deleting template."""
        # Arrange
        mock_workflow_config_service.get_board_workflow_template.return_value = (
            sample_template
        )
        mock_workflow_config_service.delete_board_workflow_template.side_effect = (
            Exception("Failed to delete from Elasticsearch cluster: connection timeout")
        )

        # Act
        response = client.delete(
            "/api/v2/projects/proj-123/board-workflows/board-001"
        )

        # Assert
        assert response.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
        data = response.json()
        assert "Elasticsearch" not in data["detail"]
        assert "connection timeout" not in data["detail"]
        assert data["detail"] == "Failed to delete template"
