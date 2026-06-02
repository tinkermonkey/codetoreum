"""Tests for MultiProjectOrchestrator admin query methods.

Tests for the admin-only functionality of MultiProjectOrchestrator:
- List enabled projects
- Get project status

Polling functionality has been removed (moved to event-driven architecture
and adapter-level polling in Phase 7).
"""

from unittest.mock import AsyncMock

import pytest

from codetoreum.application.multi_project_orchestrator import MultiProjectOrchestrator
from codetoreum.domain.value_objects import ProjectConfig
from codetoreum.ports.exceptions import ResourceNotFoundError


@pytest.fixture
def project_manager():
    """Create mock project manager."""
    return AsyncMock()


@pytest.fixture
def multi_orchestrator(project_manager):
    """Create MultiProjectOrchestrator with mocks."""
    return MultiProjectOrchestrator(
        project_manager=project_manager,
    )


class TestProjectStatus:
    """Tests for project status retrieval and listing."""

    @pytest.mark.asyncio
    async def test_get_project_status_success(self, multi_orchestrator, project_manager):
        """Test retrieving project status."""
        # Setup
        config = ProjectConfig(
            repo_url="https://github.com/acme/api-service.git",
            branch="develop",
            enabled=True,
            org="acme",
        )
        project_manager.get_project_config = AsyncMock(return_value=config)
        project_manager.get_project_path = AsyncMock(return_value="/workspace/api-service")

        # Execute
        status = await multi_orchestrator.get_project_status("api-service")

        # Assert
        assert status.project_name == "api-service"
        assert status.enabled is True
        assert status.repo_url == "https://github.com/acme/api-service.git"
        assert status.branch == "develop"
        assert status.organization == "acme"
        assert status.workspace_path == "/workspace/api-service"

    @pytest.mark.asyncio
    async def test_get_project_status_not_found(self, multi_orchestrator, project_manager):
        """Test getting status for non-existent project."""
        # Setup
        project_manager.get_project_config = AsyncMock(
            side_effect=ResourceNotFoundError("Project", "nonexistent")
        )

        # Execute & Assert
        with pytest.raises(ResourceNotFoundError):
            await multi_orchestrator.get_project_status("nonexistent")

    @pytest.mark.asyncio
    async def test_list_enabled_projects(self, multi_orchestrator, project_manager):
        """Test listing enabled projects."""
        # Setup
        project_manager.get_enabled_projects = AsyncMock(return_value=["api-service", "web-app"])

        # Execute
        projects = await multi_orchestrator.list_enabled_projects()

        # Assert
        assert projects == ["api-service", "web-app"]
        project_manager.get_enabled_projects.assert_called_once()

    @pytest.mark.asyncio
    async def test_list_enabled_projects_empty(self, multi_orchestrator, project_manager):
        """Test listing enabled projects when none exist."""
        # Setup
        project_manager.get_enabled_projects = AsyncMock(return_value=[])

        # Execute
        projects = await multi_orchestrator.list_enabled_projects()

        # Assert
        assert projects == []
        project_manager.get_enabled_projects.assert_called_once()
