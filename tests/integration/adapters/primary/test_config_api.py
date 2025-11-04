"""
Integration tests for configuration REST API endpoints.

Tests all configuration management endpoints including projects, pipelines, agents,
environment variables, search, versioning, and audit trail.
"""

import pytest
from datetime import datetime, timedelta
from typing import AsyncGenerator
from unittest.mock import AsyncMock, MagicMock

from fastapi import FastAPI, status
from fastapi.testclient import TestClient

from codetoreum.adapters.primary.routers.config import create_config_router
from codetoreum.domain.models.project_config import ProjectConfig
from codetoreum.domain.models.pipeline_config import PipelineConfig
from codetoreum.domain.models.agent_config import AgentConfig
from codetoreum.ports.input.config_command import IConfigurationCommandPort
from codetoreum.ports.input.config_query import IConfigurationQueryPort, PaginationParams


# ============================================================================
# Fixtures
# ============================================================================

@pytest.fixture
def mock_config_command_port() -> AsyncMock:
    """Create mock configuration command port for testing."""
    return AsyncMock(spec=IConfigurationCommandPort)


@pytest.fixture
def mock_config_query_port() -> AsyncMock:
    """Create mock configuration query port for testing."""
    return AsyncMock(spec=IConfigurationQueryPort)


@pytest.fixture
def test_app(
    mock_config_command_port: AsyncMock,
    mock_config_query_port: AsyncMock,
) -> FastAPI:
    """Create test FastAPI application with configuration router."""
    app = FastAPI()

    # Create router without authentication for testing
    router = create_config_router(
        command_port=mock_config_command_port,
        query_port=mock_config_query_port,
        auth_deps=None,
    )

    app.include_router(router)
    return app


@pytest.fixture
def client(test_app: FastAPI) -> TestClient:
    """Create test client for making HTTP requests."""
    return TestClient(test_app)


@pytest.fixture
def sample_project_config() -> ProjectConfig:
    """Create sample project configuration for testing."""
    return ProjectConfig(
        id="proj-123",
        name="test-project",
        description="Test project",
        github_org="test-org",
        github_repo="test-repo",
        version=1,
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
        environment_variables={"DEBUG": "true", "API_KEY": "secret123"},
        mounted_commands=["/usr/bin/npm", "/usr/bin/node"],
        mounted_subagents=["code_reviewer"],
        metadata={"team": "platform", "priority": "high"},
    )


@pytest.fixture
def sample_pipeline_config() -> PipelineConfig:
    """Create sample pipeline configuration for testing."""
    return PipelineConfig(
        id="pipeline-123",
        name="test-pipeline",
        description="Test pipeline",
        project_id="proj-123",
        version=1,
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
        stages=[
            {
                "name": "analysis",
                "agent_id": "agent-analyzer",
                "entry_conditions": {"requires_tests": False},
            },
            {
                "name": "implementation",
                "agent_id": "agent-coder",
                "entry_conditions": {"requires_approval": True},
            },
        ],
        environment_variables={"STAGE": "test"},
        metadata={"workflow_type": "ci"},
    )


@pytest.fixture
def sample_agent_config() -> AgentConfig:
    """Create sample agent configuration for testing."""
    return AgentConfig(
        id="agent-123",
        name="test-agent",
        description="Test agent",
        version=1,
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
        capabilities=["code_analysis", "bug_fix"],
        model_config={"temperature": 0.7, "max_tokens": 4000},
        mcp_servers=["artifact-server", "logging-server"],
        docker_config={
            "image": "codetoreum/agent:latest",
            "resources": {"memory": "2GB", "cpu": "1.0"},
        },
        metadata={"agent_type": "specialist"},
    )


# ============================================================================
# Project Configuration Tests
# ============================================================================

class TestProjectConfiguration:
    """Tests for project configuration endpoints."""

    @pytest.mark.asyncio
    async def test_get_project_config_success(
        self,
        client: TestClient,
        mock_config_query_port: AsyncMock,
        sample_project_config: ProjectConfig,
    ):
        """Test successfully retrieving project configuration."""
        # Arrange
        mock_config_query_port.get_project_config.return_value = sample_project_config

        # Act
        response = client.get("/api/v2/config/projects/proj-123")

        # Assert
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["id"] == "proj-123"
        assert data["name"] == "test-project"
        assert data["github_org"] == "test-org"
        assert data["github_repo"] == "test-repo"
        assert data["version"] == 1
        assert "environment_variables" in data
        mock_config_query_port.get_project_config.assert_called_once_with(
            project_id="proj-123",
            include_secrets=False,
        )

    @pytest.mark.asyncio
    async def test_get_project_config_not_found(
        self,
        client: TestClient,
        mock_config_query_port: AsyncMock,
    ):
        """Test retrieving non-existent project configuration."""
        # Arrange
        mock_config_query_port.get_project_config.side_effect = Exception("not found")

        # Act
        response = client.get("/api/v2/config/projects/nonexistent")

        # Assert
        assert response.status_code == status.HTTP_404_NOT_FOUND
        assert "not found" in response.json()["detail"].lower()

    @pytest.mark.asyncio
    async def test_update_project_config_success(
        self,
        client: TestClient,
        mock_config_command_port: AsyncMock,
    ):
        """Test successfully updating project configuration."""
        # Arrange
        mock_config_command_port.update_project_config.return_value = {
            "success": True,
            "version": 2,
        }

        # Act
        response = client.put(
            "/api/v2/config/projects/proj-123",
            json={
                "updates": {
                    "description": "Updated description",
                    "github_org": "new-org",
                },
                "reason": "Organization rename",
            },
        )

        # Assert
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["success"] is True
        assert data["version"] == 2

    @pytest.mark.asyncio
    async def test_update_project_config_validation_error(
        self,
        client: TestClient,
        mock_config_command_port: AsyncMock,
    ):
        """Test updating project configuration with invalid data."""
        # Arrange
        mock_config_command_port.update_project_config.side_effect = ValueError(
            "Invalid configuration"
        )

        # Act
        response = client.put(
            "/api/v2/config/projects/proj-123",
            json={
                "updates": {"invalid_field": "value"},
            },
        )

        # Assert
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    @pytest.mark.asyncio
    async def test_list_projects_with_pagination(
        self,
        client: TestClient,
        mock_config_query_port: AsyncMock,
        sample_project_config: ProjectConfig,
    ):
        """Test listing projects with pagination."""
        # Arrange
        mock_config_query_port.list_projects.return_value = {
            "items": [sample_project_config],
            "total": 1,
            "page": 1,
            "page_size": 20,
        }

        # Act
        response = client.get("/api/v2/config/projects?page=1&page_size=20")

        # Assert
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert len(data["items"]) == 1
        assert data["total"] == 1
        assert data["page"] == 1

    @pytest.mark.asyncio
    async def test_list_projects_empty_result(
        self,
        client: TestClient,
        mock_config_query_port: AsyncMock,
    ):
        """Test listing projects when no projects exist."""
        # Arrange
        mock_config_query_port.list_projects.return_value = {
            "items": [],
            "total": 0,
            "page": 1,
            "page_size": 20,
        }

        # Act
        response = client.get("/api/v2/config/projects")

        # Assert
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert len(data["items"]) == 0
        assert data["total"] == 0


# ============================================================================
# Pipeline Configuration Tests
# ============================================================================

class TestPipelineConfiguration:
    """Tests for pipeline configuration endpoints."""

    @pytest.mark.asyncio
    async def test_get_pipeline_config_success(
        self,
        client: TestClient,
        mock_config_query_port: AsyncMock,
        sample_pipeline_config: PipelineConfig,
    ):
        """Test successfully retrieving pipeline configuration."""
        # Arrange
        mock_config_query_port.get_pipeline_config.return_value = sample_pipeline_config

        # Act
        response = client.get("/api/v2/config/pipelines/pipeline-123")

        # Assert
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["id"] == "pipeline-123"
        assert data["name"] == "test-pipeline"
        assert len(data["stages"]) == 2
        assert data["stages"][0]["name"] == "analysis"

    @pytest.mark.asyncio
    async def test_update_pipeline_config_add_stage(
        self,
        client: TestClient,
        mock_config_command_port: AsyncMock,
    ):
        """Test adding a stage to pipeline configuration."""
        # Arrange
        mock_config_command_port.update_pipeline_config.return_value = {
            "success": True,
            "version": 2,
        }

        # Act
        response = client.put(
            "/api/v2/config/pipelines/pipeline-123",
            json={
                "updates": {
                    "stages": [
                        {"name": "analysis", "agent_id": "agent-analyzer"},
                        {"name": "implementation", "agent_id": "agent-coder"},
                        {"name": "review", "agent_id": "agent-reviewer"},
                    ],
                },
                "reason": "Added review stage",
            },
        )

        # Assert
        assert response.status_code == status.HTTP_200_OK

    @pytest.mark.asyncio
    async def test_list_pipelines_filtered_by_project(
        self,
        client: TestClient,
        mock_config_query_port: AsyncMock,
        sample_pipeline_config: PipelineConfig,
    ):
        """Test listing pipelines filtered by project."""
        # Arrange
        mock_config_query_port.list_pipelines.return_value = {
            "items": [sample_pipeline_config],
            "total": 1,
        }

        # Act
        response = client.get("/api/v2/config/pipelines?project_id=proj-123")

        # Assert
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert len(data["items"]) == 1
        assert data["items"][0]["project_id"] == "proj-123"


# ============================================================================
# Agent Configuration Tests
# ============================================================================

class TestAgentConfiguration:
    """Tests for agent configuration endpoints."""

    @pytest.mark.asyncio
    async def test_get_agent_config_success(
        self,
        client: TestClient,
        mock_config_query_port: AsyncMock,
        sample_agent_config: AgentConfig,
    ):
        """Test successfully retrieving agent configuration."""
        # Arrange
        mock_config_query_port.get_agent_config.return_value = sample_agent_config

        # Act
        response = client.get("/api/v2/config/agents/agent-123")

        # Assert
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["id"] == "agent-123"
        assert data["name"] == "test-agent"
        assert "code_analysis" in data["capabilities"]

    @pytest.mark.asyncio
    async def test_update_agent_config_capabilities(
        self,
        client: TestClient,
        mock_config_command_port: AsyncMock,
    ):
        """Test updating agent capabilities."""
        # Arrange
        mock_config_command_port.update_agent_config.return_value = {
            "success": True,
            "version": 2,
        }

        # Act
        response = client.put(
            "/api/v2/config/agents/agent-123",
            json={
                "updates": {
                    "capabilities": ["code_analysis", "bug_fix", "refactoring"],
                },
            },
        )

        # Assert
        assert response.status_code == status.HTTP_200_OK

    @pytest.mark.asyncio
    async def test_update_agent_config_model_params(
        self,
        client: TestClient,
        mock_config_command_port: AsyncMock,
    ):
        """Test updating agent model parameters."""
        # Arrange
        mock_config_command_port.update_agent_config.return_value = {
            "success": True,
            "version": 2,
        }

        # Act
        response = client.put(
            "/api/v2/config/agents/agent-123",
            json={
                "updates": {
                    "model_config": {
                        "temperature": 0.8,
                        "max_tokens": 8000,
                    },
                },
            },
        )

        # Assert
        assert response.status_code == status.HTTP_200_OK


# ============================================================================
# Environment Variable Tests
# ============================================================================

class TestEnvironmentVariables:
    """Tests for environment variable management endpoints."""

    @pytest.mark.asyncio
    async def test_add_environment_variable_project_scope(
        self,
        client: TestClient,
        mock_config_command_port: AsyncMock,
    ):
        """Test adding environment variable with project scope."""
        # Arrange
        mock_config_command_port.add_environment_variable.return_value = {
            "success": True,
        }

        # Act
        response = client.post(
            "/api/v2/config/environment-variables",
            json={
                "scope": "project",
                "scope_id": "proj-123",
                "name": "API_KEY",
                "value": "secret123",
                "is_secret": True,
                "description": "API key for external service",
            },
        )

        # Assert
        assert response.status_code == status.HTTP_200_OK

    @pytest.mark.asyncio
    async def test_add_environment_variable_pipeline_scope(
        self,
        client: TestClient,
        mock_config_command_port: AsyncMock,
    ):
        """Test adding environment variable with pipeline scope."""
        # Arrange
        mock_config_command_port.add_environment_variable.return_value = {
            "success": True,
        }

        # Act
        response = client.post(
            "/api/v2/config/environment-variables",
            json={
                "scope": "pipeline",
                "scope_id": "pipeline-123",
                "name": "STAGE",
                "value": "production",
                "is_secret": False,
            },
        )

        # Assert
        assert response.status_code == status.HTTP_200_OK

    @pytest.mark.asyncio
    async def test_remove_environment_variable(
        self,
        client: TestClient,
        mock_config_command_port: AsyncMock,
    ):
        """Test removing environment variable."""
        # Arrange
        mock_config_command_port.remove_environment_variable.return_value = {
            "success": True,
        }

        # Act
        response = client.delete(
            "/api/v2/config/environment-variables",
            json={
                "scope": "project",
                "scope_id": "proj-123",
                "name": "OLD_VAR",
            },
        )

        # Assert
        assert response.status_code == status.HTTP_200_OK

    @pytest.mark.asyncio
    async def test_list_environment_variables_by_scope(
        self,
        client: TestClient,
        mock_config_query_port: AsyncMock,
    ):
        """Test listing environment variables filtered by scope."""
        # Arrange
        mock_config_query_port.list_environment_variables.return_value = [
            {"name": "API_KEY", "value": "***", "is_secret": True},
            {"name": "DEBUG", "value": "true", "is_secret": False},
        ]

        # Act
        response = client.get(
            "/api/v2/config/environment-variables?scope=project&scope_id=proj-123"
        )

        # Assert
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert len(data) == 2


# ============================================================================
# Configuration Search Tests
# ============================================================================

class TestConfigurationSearch:
    """Tests for configuration search endpoints."""

    @pytest.mark.asyncio
    async def test_search_configs_by_keyword(
        self,
        client: TestClient,
        mock_config_query_port: AsyncMock,
    ):
        """Test searching configurations by keyword."""
        # Arrange
        mock_config_query_port.search_configs.return_value = {
            "results": [
                {
                    "type": "project",
                    "id": "proj-123",
                    "name": "test-project",
                    "match_field": "description",
                    "match_value": "Contains test keyword",
                }
            ],
            "total": 1,
        }

        # Act
        response = client.post(
            "/api/v2/config/search",
            json={
                "keyword": "test",
                "config_types": ["project", "pipeline"],
            },
        )

        # Assert
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["total"] == 1
        assert data["results"][0]["type"] == "project"

    @pytest.mark.asyncio
    async def test_search_configs_filtered_by_type(
        self,
        client: TestClient,
        mock_config_query_port: AsyncMock,
    ):
        """Test searching configurations filtered by type."""
        # Arrange
        mock_config_query_port.search_configs.return_value = {
            "results": [],
            "total": 0,
        }

        # Act
        response = client.post(
            "/api/v2/config/search",
            json={
                "keyword": "nonexistent",
                "config_types": ["agent"],
            },
        )

        # Assert
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["total"] == 0


# ============================================================================
# Configuration Versioning Tests
# ============================================================================

class TestConfigurationVersioning:
    """Tests for configuration versioning and audit trail."""

    @pytest.mark.asyncio
    async def test_get_config_version_history(
        self,
        client: TestClient,
        mock_config_query_port: AsyncMock,
    ):
        """Test retrieving configuration version history."""
        # Arrange
        mock_config_query_port.get_version_history.return_value = {
            "versions": [
                {
                    "version": 2,
                    "timestamp": datetime.utcnow().isoformat(),
                    "changes": {"description": "Updated"},
                    "reason": "User update",
                },
                {
                    "version": 1,
                    "timestamp": (datetime.utcnow() - timedelta(days=1)).isoformat(),
                    "changes": {},
                    "reason": "Initial creation",
                },
            ],
            "total": 2,
        }

        # Act
        response = client.get("/api/v2/config/projects/proj-123/history")

        # Assert
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert len(data["versions"]) == 2
        assert data["versions"][0]["version"] == 2

    @pytest.mark.asyncio
    async def test_rollback_to_previous_version(
        self,
        client: TestClient,
        mock_config_command_port: AsyncMock,
    ):
        """Test rolling back configuration to previous version."""
        # Arrange
        mock_config_command_port.rollback_to_version.return_value = {
            "success": True,
            "version": 3,
        }

        # Act
        response = client.post(
            "/api/v2/config/projects/proj-123/rollback",
            json={
                "target_version": 1,
                "reason": "Reverting problematic changes",
            },
        )

        # Assert
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["success"] is True


# ============================================================================
# Configuration Import/Export Tests
# ============================================================================

class TestConfigurationImportExport:
    """Tests for configuration import and export endpoints."""

    @pytest.mark.asyncio
    async def test_export_project_config(
        self,
        client: TestClient,
        mock_config_query_port: AsyncMock,
    ):
        """Test exporting project configuration."""
        # Arrange
        mock_config_query_port.export_project_config.return_value = {
            "format": "json",
            "data": {"id": "proj-123", "name": "test-project"},
        }

        # Act
        response = client.get("/api/v2/config/projects/proj-123/export?format=json")

        # Assert
        assert response.status_code == status.HTTP_200_OK

    @pytest.mark.asyncio
    async def test_import_project_config(
        self,
        client: TestClient,
        mock_config_command_port: AsyncMock,
    ):
        """Test importing project configuration."""
        # Arrange
        mock_config_command_port.import_project_config.return_value = {
            "success": True,
            "project_id": "proj-456",
        }

        # Act
        response = client.post(
            "/api/v2/config/projects/import",
            json={
                "format": "json",
                "data": {"name": "imported-project", "description": "Imported"},
            },
        )

        # Assert
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["success"] is True


# ============================================================================
# Concurrent Operations Tests
# ============================================================================

class TestConcurrentOperations:
    """Tests for handling concurrent configuration updates."""

    @pytest.mark.asyncio
    async def test_concurrent_updates_version_conflict(
        self,
        client: TestClient,
        mock_config_command_port: AsyncMock,
    ):
        """Test handling version conflict during concurrent updates."""
        # Arrange
        mock_config_command_port.update_project_config.side_effect = Exception(
            "Version conflict: configuration was modified"
        )

        # Act
        response = client.put(
            "/api/v2/config/projects/proj-123",
            json={
                "updates": {"description": "Update 1"},
                "expected_version": 1,
            },
        )

        # Assert
        assert response.status_code == status.HTTP_409_CONFLICT

    @pytest.mark.asyncio
    async def test_optimistic_locking_success(
        self,
        client: TestClient,
        mock_config_command_port: AsyncMock,
    ):
        """Test successful update with optimistic locking."""
        # Arrange
        mock_config_command_port.update_project_config.return_value = {
            "success": True,
            "version": 2,
        }

        # Act
        response = client.put(
            "/api/v2/config/projects/proj-123",
            json={
                "updates": {"description": "Update"},
                "expected_version": 1,
            },
        )

        # Assert
        assert response.status_code == status.HTTP_200_OK


# ============================================================================
# Global Settings Tests
# ============================================================================

class TestGlobalSettings:
    """Tests for global settings endpoints."""

    @pytest.mark.asyncio
    async def test_get_global_settings(
        self,
        client: TestClient,
        mock_config_query_port: AsyncMock,
    ):
        """Test retrieving global settings."""
        # Arrange
        mock_config_query_port.get_global_settings.return_value = {
            "max_concurrent_executions": 5,
            "default_timeout_seconds": 3600,
            "retry_policy": {"max_attempts": 3, "backoff_multiplier": 2},
        }

        # Act
        response = client.get("/api/v2/config/global-settings")

        # Assert
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["max_concurrent_executions"] == 5

    @pytest.mark.asyncio
    async def test_update_global_settings(
        self,
        client: TestClient,
        mock_config_command_port: AsyncMock,
    ):
        """Test updating global settings."""
        # Arrange
        mock_config_command_port.update_global_settings.return_value = {
            "success": True,
        }

        # Act
        response = client.put(
            "/api/v2/config/global-settings",
            json={
                "updates": {
                    "max_concurrent_executions": 10,
                },
            },
        )

        # Assert
        assert response.status_code == status.HTTP_200_OK
