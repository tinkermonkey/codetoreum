"""
Integration tests for configuration REST API endpoints.

Tests all configuration management endpoints including projects, pipelines, agents,
environment variables, search, versioning, and audit trail.
"""

import pytest
from datetime import datetime, timedelta, timezone
from typing import AsyncGenerator
from unittest.mock import AsyncMock, MagicMock

from fastapi import FastAPI, status
from fastapi.testclient import TestClient

from codetoreum.adapters.primary.routers.config import create_config_router
from codetoreum.ports.input.config_command import IConfigurationCommandPort
from codetoreum.ports.input.config_query import (
    IConfigurationQueryPort,
    PaginationParams,
    ProjectConfigInfo,
    PipelineConfigInfo,
    AgentConfigInfo,
)


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
    with TestClient(test_app) as test_client:
        yield test_client


@pytest.fixture
def sample_project_config() -> ProjectConfigInfo:
    """Create sample project configuration for testing."""
    return ProjectConfigInfo(
        id="proj-123",
        name="test-project",
        description="Test project",
        github_org="test-org",
        github_repo="test-repo",
        version=1,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
        environment_variables={"DEBUG": "true", "API_KEY": "secret123"},
        mounted_commands=[],
        mounted_subagents=[],
        metadata={"team": "platform", "priority": "high"},
    )


@pytest.fixture
def sample_pipeline_config() -> PipelineConfigInfo:
    """Create sample pipeline configuration for testing."""
    return PipelineConfigInfo(
        id="pipeline-123",
        name="test-pipeline",
        description="Test pipeline",
        project_id="proj-123",
        version=1,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
        stages=[
            {
                "name": "analysis",
                "agent_name": "agent-analyzer",
                "timeout_seconds": 3600,
                "retry_count": 3,
                "entry_conditions": [],
                "metadata": {},
            },
            {
                "name": "implementation",
                "agent_name": "agent-coder",
                "timeout_seconds": 3600,
                "retry_count": 3,
                "entry_conditions": [],
                "metadata": {},
            },
        ],
        metadata={"workflow_type": "ci"},
    )


@pytest.fixture
def sample_agent_config() -> AgentConfigInfo:
    """Create sample agent configuration for testing."""
    return AgentConfigInfo(
        project_id="proj-123",
        agent_name="test-agent",
        display_name="Test Agent",
        model="claude-sonnet-4",
        timeout_seconds=3600,
        max_retries=3,
        requires_docker=True,
        requires_dev_container=False,
        makes_code_changes=True,
        filesystem_write_allowed=True,
        version=1,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
        mcp_servers=[],
        capabilities={"code_analysis": True, "bug_fix": True},
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
        sample_project_config: ProjectConfigInfo,
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
        from codetoreum.ports.input.exceptions import ProjectNotFoundError

        mock_config_query_port.get_project_config.side_effect = ProjectNotFoundError("Project not found")

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
        mock_config_query_port: AsyncMock,
        sample_project_config: ProjectConfigInfo,
    ):
        """Test successfully updating project configuration."""
        # Arrange
        mock_config_query_port.get_project_config.return_value = sample_project_config
        mock_config_command_port.update_project_config.return_value = MagicMock(
            success=True,
            config_version=2,
            message="Updated",
            changes_applied={"description": "Updated description", "github_org": "new-org"},
            errors=None,
        )

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
        assert data["config_version"] == 2

    @pytest.mark.asyncio
    async def test_update_project_config_validation_error(
        self,
        client: TestClient,
        mock_config_command_port: AsyncMock,
        mock_config_query_port: AsyncMock,
        sample_project_config: ProjectConfigInfo,
    ):
        """Test updating project configuration with invalid data."""
        # Arrange
        from codetoreum.ports.input.exceptions import ValidationError

        mock_config_query_port.get_project_config.return_value = sample_project_config
        mock_config_command_port.update_project_config.side_effect = ValidationError(
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
        sample_project_config: ProjectConfigInfo,
    ):
        """Test listing projects with pagination."""
        # Arrange
        mock_config_query_port.list_projects.return_value = [sample_project_config]
        mock_config_query_port.count_configs.return_value = 1

        # Act
        response = client.get("/api/v2/config/projects?offset=0&limit=20")

        # Assert
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert len(data["projects"]) == 1
        assert data["total_count"] == 1

    @pytest.mark.asyncio
    async def test_list_projects_empty_result(
        self,
        client: TestClient,
        mock_config_query_port: AsyncMock,
    ):
        """Test listing projects when no projects exist."""
        # Arrange
        mock_config_query_port.list_projects.return_value = []
        mock_config_query_port.count_configs.return_value = 0

        # Act
        response = client.get("/api/v2/config/projects")

        # Assert
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert len(data["projects"]) == 0
        assert data["total_count"] == 0


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
        sample_pipeline_config: PipelineConfigInfo,
    ):
        """Test successfully retrieving pipeline configuration."""
        # Arrange
        mock_config_query_port.get_pipeline_config.return_value = sample_pipeline_config

        # Act
        response = client.get("/api/v2/config/projects/proj-123/pipelines/test-pipeline")

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
        mock_config_query_port: AsyncMock,
        sample_project_config: ProjectConfigInfo,
    ):
        """Test adding a stage to pipeline configuration."""
        # Arrange
        mock_config_query_port.get_project_config.return_value = sample_project_config
        mock_config_command_port.update_pipeline_config.return_value = MagicMock(
            success=True,
            config_version=2,
            message="Updated",
            changes_applied={"stages": "added review stage"},
            errors=None,
        )

        # Act
        response = client.put(
            "/api/v2/config/projects/proj-123/pipelines/test-pipeline",
            json={
                "updates": {
                    "stages": [
                        {"name": "analysis", "agent_name": "agent-analyzer"},
                        {"name": "implementation", "agent_name": "agent-coder"},
                        {"name": "review", "agent_name": "agent-reviewer"},
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
        sample_pipeline_config: PipelineConfigInfo,
    ):
        """Test listing pipelines filtered by project."""
        # Arrange
        mock_config_query_port.list_pipelines.return_value = [sample_pipeline_config]
        mock_config_query_port.count_configs.return_value = 1

        # Act
        response = client.get("/api/v2/config/projects/proj-123/pipelines")

        # Assert
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert len(data["pipelines"]) == 1
        assert data["pipelines"][0]["project_id"] == "proj-123"


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
        sample_agent_config: AgentConfigInfo,
    ):
        """Test successfully retrieving agent configuration."""
        # Arrange
        mock_config_query_port.get_agent_config.return_value = sample_agent_config

        # Act
        response = client.get("/api/v2/config/projects/proj-123/agents/test-agent")

        # Assert
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["project_id"] == "proj-123"
        assert data["agent_name"] == "test-agent"
        assert data["capabilities"] is not None

    @pytest.mark.asyncio
    async def test_update_agent_config_capabilities(
        self,
        client: TestClient,
        mock_config_command_port: AsyncMock,
        mock_config_query_port: AsyncMock,
        sample_project_config: ProjectConfigInfo,
    ):
        """Test updating agent capabilities."""
        # Arrange
        mock_config_query_port.get_project_config.return_value = sample_project_config
        mock_config_command_port.update_agent_config.return_value = MagicMock(
            success=True,
            config_version=2,
            message="Updated",
            changes_applied={"capabilities": ["code_analysis", "bug_fix", "refactoring"]},
            errors=None,
        )

        # Act
        response = client.put(
            "/api/v2/config/projects/proj-123/agents/test-agent",
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
        mock_config_query_port: AsyncMock,
        sample_project_config: ProjectConfigInfo,
    ):
        """Test updating agent model parameters."""
        # Arrange
        mock_config_query_port.get_project_config.return_value = sample_project_config
        mock_config_command_port.update_agent_config.return_value = MagicMock(
            success=True,
            config_version=2,
            message="Updated",
            changes_applied={"model": "claude-opus-4"},
            errors=None,
        )

        # Act
        response = client.put(
            "/api/v2/config/projects/proj-123/agents/test-agent",
            json={
                "updates": {
                    "model": "claude-opus-4",
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
        mock_config_query_port: AsyncMock,
        sample_project_config: ProjectConfigInfo,
    ):
        """Test adding environment variable with project scope."""
        # Arrange
        mock_config_query_port.get_project_config.return_value = sample_project_config
        mock_config_command_port.add_environment_variable.return_value = MagicMock(
            success=True,
            config_version=2,
            message="Added",
            changes_applied={"API_KEY": "***"},
            errors=None,
        )

        # Act
        response = client.post(
            "/api/v2/config/projects/proj-123/env-vars",
            json={
                "variable_name": "API_KEY",
                "variable_value": "secret123",
                "is_secret": True,
                "description": "API key for external service",
            },
        )

        # Assert
        assert response.status_code == status.HTTP_201_CREATED


    @pytest.mark.asyncio
    async def test_remove_environment_variable(
        self,
        client: TestClient,
        mock_config_command_port: AsyncMock,
        mock_config_query_port: AsyncMock,
        sample_project_config: ProjectConfigInfo,
    ):
        """Test removing environment variable."""
        # Arrange
        mock_config_query_port.get_project_config.return_value = sample_project_config
        mock_config_command_port.remove_environment_variable.return_value = MagicMock(
            success=True,
            config_version=2,
            message="Removed",
            changes_applied={"removed": "OLD_VAR"},
            errors=None,
        )

        # Act
        response = client.delete("/api/v2/config/projects/proj-123/env-vars/OLD_VAR")

        # Assert
        assert response.status_code == status.HTTP_200_OK


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
        from codetoreum.ports.input.config_query import ConfigSearchResult, ConfigSearchResults

        search_result = ConfigSearchResult(
            config_id="proj-123",
            config_type="project",
            name="test-project",
            description="Contains test keyword",
            matched_fields=["description"],
            score=0.95,
        )
        mock_config_query_port.search_configs.return_value = ConfigSearchResults(
            results=[search_result],
            total_count=1,
            query="test",
            filters={},
        )

        # Act
        response = client.get("/api/v2/config/search?query=test")

        # Assert
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["total_count"] == 1
        assert data["results"][0]["config_type"] == "project"

    @pytest.mark.asyncio
    async def test_search_configs_filtered_by_type(
        self,
        client: TestClient,
        mock_config_query_port: AsyncMock,
    ):
        """Test searching configurations filtered by type."""
        # Arrange
        from codetoreum.ports.input.config_query import ConfigSearchResults

        mock_config_query_port.search_configs.return_value = ConfigSearchResults(
            results=[],
            total_count=0,
            query="nonexistent",
            filters={"config_type": "agent"},
        )

        # Act
        response = client.get("/api/v2/config/search?query=nonexistent&config_type=agent")

        # Assert
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["total_count"] == 0


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
        sample_project_config: ProjectConfigInfo,
    ):
        """Test retrieving configuration version history."""
        # Arrange
        from codetoreum.ports.input.config_query import ConfigVersionInfo

        version_history = [
            ConfigVersionInfo(
                version=2,
                created_at=datetime.now(timezone.utc),
                created_by="user@example.com",
                changes={"description": "Updated"},
                reason="User update",
            ),
            ConfigVersionInfo(
                version=1,
                created_at=datetime.now(timezone.utc) - timedelta(days=1),
                created_by="admin@example.com",
                changes={},
                reason="Initial creation",
            ),
        ]
        mock_config_query_port.get_config_version_history.return_value = version_history
        mock_config_query_port.get_project_config.return_value = sample_project_config

        # Act
        response = client.get("/api/v2/config/projects/proj-123/history")

        # Assert
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert len(data["history"]) == 2
        assert data["history"][0]["version"] == 2

