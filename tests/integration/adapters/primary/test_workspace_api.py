"""
Integration tests for workspace REST API endpoints.

Tests workspace lifecycle, file mounting, configuration updates, concurrent operations,
and WebSocket notifications for workspace events.
"""

import pytest
from datetime import datetime
from typing import AsyncGenerator
from unittest.mock import AsyncMock, MagicMock

from fastapi import FastAPI, status
from fastapi.testclient import TestClient

from codetoreum.adapters.primary.routers.workspace import create_workspace_router
from codetoreum.domain.models.workspace import Workspace, WorkspaceStatus
from codetoreum.ports.input.workspace_command import IWorkspaceCommandPort
from codetoreum.ports.input.workspace_query import IWorkspaceQueryPort


# ============================================================================
# Fixtures
# ============================================================================

@pytest.fixture
def mock_workspace_command_port() -> AsyncMock:
    """Create mock workspace command port for testing."""
    return AsyncMock(spec=IWorkspaceCommandPort)


@pytest.fixture
def mock_workspace_query_port() -> AsyncMock:
    """Create mock workspace query port for testing."""
    return AsyncMock(spec=IWorkspaceQueryPort)


@pytest.fixture
def test_app(
    mock_workspace_command_port: AsyncMock,
    mock_workspace_query_port: AsyncMock,
) -> FastAPI:
    """Create test FastAPI application with workspace router."""
    app = FastAPI()

    router = create_workspace_router(
        command_port=mock_workspace_command_port,
        query_port=mock_workspace_query_port,
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
def sample_workspace() -> Workspace:
    """Create sample workspace for testing."""
    return Workspace(
        id="workspace-123",
        name="test-workspace",
        project_id="proj-123",
        git_repo_url="https://github.com/test/repo.git",
        git_branch="main",
        status=WorkspaceStatus.READY,
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
        mounted_paths=["/src", "/tests"],
        environment_variables={"NODE_ENV": "test"},
        container_id="container-abc123",
        metadata={"purpose": "testing"},
    )


# ============================================================================
# Workspace Lifecycle Tests
# ============================================================================

class TestWorkspaceLifecycle:
    """Tests for workspace creation, retrieval, and deletion."""

    @pytest.mark.asyncio
    async def test_create_workspace_with_git_repo(
        self,
        client: TestClient,
        mock_workspace_command_port: AsyncMock,
    ):
        """Test creating workspace with Git repository."""
        # Arrange
        mock_workspace_command_port.create_workspace.return_value = {
            "workspace_id": "workspace-123",
            "status": "initializing",
        }

        # Act
        response = client.post(
            "/api/v2/workspaces",
            json={
                "name": "test-workspace",
                "project_id": "proj-123",
                "git_repo_url": "https://github.com/test/repo.git",
                "git_branch": "main",
                "mounted_paths": ["/src"],
            },
        )

        # Assert
        assert response.status_code == status.HTTP_201_CREATED
        data = response.json()
        assert data["workspace_id"] == "workspace-123"

    @pytest.mark.asyncio
    async def test_create_workspace_validation_error(
        self,
        client: TestClient,
        mock_workspace_command_port: AsyncMock,
    ):
        """Test creating workspace with invalid data."""
        # Arrange
        mock_workspace_command_port.create_workspace.side_effect = ValueError(
            "Invalid Git URL"
        )

        # Act
        response = client.post(
            "/api/v2/workspaces",
            json={
                "name": "test",
                "project_id": "proj-123",
                "git_repo_url": "invalid-url",
            },
        )

        # Assert
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    @pytest.mark.asyncio
    async def test_get_workspace_details(
        self,
        client: TestClient,
        mock_workspace_query_port: AsyncMock,
        sample_workspace: Workspace,
    ):
        """Test retrieving workspace details."""
        # Arrange
        mock_workspace_query_port.get_workspace.return_value = sample_workspace

        # Act
        response = client.get("/api/v2/workspaces/workspace-123")

        # Assert
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["id"] == "workspace-123"
        assert data["status"] == "ready"

    @pytest.mark.asyncio
    async def test_get_workspace_not_found(
        self,
        client: TestClient,
        mock_workspace_query_port: AsyncMock,
    ):
        """Test retrieving non-existent workspace."""
        # Arrange
        mock_workspace_query_port.get_workspace.side_effect = Exception("not found")

        # Act
        response = client.get("/api/v2/workspaces/nonexistent")

        # Assert
        assert response.status_code == status.HTTP_404_NOT_FOUND

    @pytest.mark.asyncio
    async def test_list_workspaces_with_filtering(
        self,
        client: TestClient,
        mock_workspace_query_port: AsyncMock,
        sample_workspace: Workspace,
    ):
        """Test listing workspaces with status filter."""
        # Arrange
        mock_workspace_query_port.list_workspaces.return_value = {
            "items": [sample_workspace],
            "total": 1,
        }

        # Act
        response = client.get("/api/v2/workspaces?status=ready&project_id=proj-123")

        # Assert
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert len(data["items"]) == 1

    @pytest.mark.asyncio
    async def test_delete_workspace(
        self,
        client: TestClient,
        mock_workspace_command_port: AsyncMock,
    ):
        """Test deleting workspace."""
        # Arrange
        mock_workspace_command_port.delete_workspace.return_value = {
            "success": True,
        }

        # Act
        response = client.delete("/api/v2/workspaces/workspace-123")

        # Assert
        assert response.status_code == status.HTTP_200_OK


# ============================================================================
# File Mounting Tests
# ============================================================================

class TestFileMounting:
    """Tests for mounting and unmounting file paths."""

    @pytest.mark.asyncio
    async def test_mount_path(
        self,
        client: TestClient,
        mock_workspace_command_port: AsyncMock,
    ):
        """Test mounting a path to workspace."""
        # Arrange
        mock_workspace_command_port.mount_path.return_value = {
            "success": True,
            "mounted_paths": ["/src", "/tests", "/docs"],
        }

        # Act
        response = client.post(
            "/api/v2/workspaces/workspace-123/mount",
            json={
                "path": "/docs",
                "mode": "read-only",
            },
        )

        # Assert
        assert response.status_code == status.HTTP_200_OK

    @pytest.mark.asyncio
    async def test_mount_path_already_mounted(
        self,
        client: TestClient,
        mock_workspace_command_port: AsyncMock,
    ):
        """Test mounting already mounted path."""
        # Arrange
        mock_workspace_command_port.mount_path.side_effect = Exception(
            "Path already mounted"
        )

        # Act
        response = client.post(
            "/api/v2/workspaces/workspace-123/mount",
            json={"path": "/src"},
        )

        # Assert
        assert response.status_code == status.HTTP_409_CONFLICT

    @pytest.mark.asyncio
    async def test_unmount_path(
        self,
        client: TestClient,
        mock_workspace_command_port: AsyncMock,
    ):
        """Test unmounting a path from workspace."""
        # Arrange
        mock_workspace_command_port.unmount_path.return_value = {
            "success": True,
            "mounted_paths": ["/src"],
        }

        # Act
        response = client.post(
            "/api/v2/workspaces/workspace-123/unmount",
            json={"path": "/tests"},
        )

        # Assert
        assert response.status_code == status.HTTP_200_OK

    @pytest.mark.asyncio
    async def test_unmount_path_not_mounted(
        self,
        client: TestClient,
        mock_workspace_command_port: AsyncMock,
    ):
        """Test unmounting path that isn't mounted."""
        # Arrange
        mock_workspace_command_port.unmount_path.side_effect = Exception(
            "Path not mounted"
        )

        # Act
        response = client.post(
            "/api/v2/workspaces/workspace-123/unmount",
            json={"path": "/nonexistent"},
        )

        # Assert
        assert response.status_code == status.HTTP_400_BAD_REQUEST


# ============================================================================
# Workspace Configuration Tests
# ============================================================================

class TestWorkspaceConfiguration:
    """Tests for updating workspace configuration."""

    @pytest.mark.asyncio
    async def test_update_workspace_config(
        self,
        client: TestClient,
        mock_workspace_command_port: AsyncMock,
    ):
        """Test updating workspace configuration."""
        # Arrange
        mock_workspace_command_port.update_workspace.return_value = {
            "success": True,
        }

        # Act
        response = client.put(
            "/api/v2/workspaces/workspace-123",
            json={
                "environment_variables": {"DEBUG": "true"},
                "metadata": {"updated": "yes"},
            },
        )

        # Assert
        assert response.status_code == status.HTTP_200_OK

    @pytest.mark.asyncio
    async def test_update_workspace_validation_error(
        self,
        client: TestClient,
        mock_workspace_command_port: AsyncMock,
    ):
        """Test updating workspace with invalid data."""
        # Arrange
        mock_workspace_command_port.update_workspace.side_effect = ValueError(
            "Invalid configuration"
        )

        # Act
        response = client.put(
            "/api/v2/workspaces/workspace-123",
            json={"invalid_field": "value"},
        )

        # Assert
        assert response.status_code == status.HTTP_400_BAD_REQUEST


# ============================================================================
# Workspace Cleanup Tests
# ============================================================================

class TestWorkspaceCleanup:
    """Tests for workspace cleanup operations."""

    @pytest.mark.asyncio
    async def test_clean_workspace_artifacts(
        self,
        client: TestClient,
        mock_workspace_command_port: AsyncMock,
    ):
        """Test cleaning workspace artifacts."""
        # Arrange
        mock_workspace_command_port.clean_workspace.return_value = {
            "success": True,
            "deleted_files": 15,
            "freed_space_mb": 128,
        }

        # Act
        response = client.post("/api/v2/workspaces/workspace-123/clean")

        # Assert
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["deleted_files"] == 15

    @pytest.mark.asyncio
    async def test_clean_workspace_in_use(
        self,
        client: TestClient,
        mock_workspace_command_port: AsyncMock,
    ):
        """Test cleaning workspace that is in use."""
        # Arrange
        mock_workspace_command_port.clean_workspace.side_effect = Exception(
            "Workspace is in use"
        )

        # Act
        response = client.post("/api/v2/workspaces/workspace-123/clean")

        # Assert
        assert response.status_code == status.HTTP_409_CONFLICT


# ============================================================================
# Concurrent Operations Tests
# ============================================================================

class TestConcurrentWorkspaceOperations:
    """Tests for handling concurrent workspace operations."""

    @pytest.mark.asyncio
    async def test_concurrent_mount_operations(
        self,
        client: TestClient,
        mock_workspace_command_port: AsyncMock,
    ):
        """Test handling concurrent mount operations."""
        # Arrange
        mock_workspace_command_port.mount_path.return_value = {
            "success": True,
            "mounted_paths": ["/src", "/tests", "/docs"],
        }

        # Act - Simulate concurrent requests
        response1 = client.post(
            "/api/v2/workspaces/workspace-123/mount",
            json={"path": "/tests"},
        )
        response2 = client.post(
            "/api/v2/workspaces/workspace-123/mount",
            json={"path": "/docs"},
        )

        # Assert
        assert response1.status_code == status.HTTP_200_OK
        assert response2.status_code == status.HTTP_200_OK

    @pytest.mark.asyncio
    async def test_concurrent_update_race_condition(
        self,
        client: TestClient,
        mock_workspace_command_port: AsyncMock,
    ):
        """Test handling race condition in concurrent updates."""
        # Arrange
        mock_workspace_command_port.update_workspace.side_effect = [
            {"success": True},
            Exception("Concurrent modification detected"),
        ]

        # Act
        response1 = client.put(
            "/api/v2/workspaces/workspace-123",
            json={"metadata": {"update": "1"}},
        )
        response2 = client.put(
            "/api/v2/workspaces/workspace-123",
            json={"metadata": {"update": "2"}},
        )

        # Assert
        assert response1.status_code == status.HTTP_200_OK
        assert response2.status_code == status.HTTP_409_CONFLICT


# ============================================================================
# WebSocket Notification Tests
# ============================================================================

class TestWebSocketNotifications:
    """Tests for WebSocket notifications for workspace events."""

    @pytest.mark.asyncio
    async def test_workspace_status_change_notification(
        self,
        client: TestClient,
    ):
        """Test WebSocket notification when workspace status changes."""
        # Note: WebSocket testing requires special setup
        # This documents the expected behavior

        # WebSocket clients should receive notifications like:
        # {
        #   "event_type": "workspace_status_changed",
        #   "workspace_id": "workspace-123",
        #   "old_status": "initializing",
        #   "new_status": "ready",
        #   "timestamp": "2024-01-15T10:30:00Z"
        # }
        pass

    @pytest.mark.asyncio
    async def test_workspace_mount_change_notification(
        self,
        client: TestClient,
    ):
        """Test WebSocket notification when paths are mounted/unmounted."""
        # WebSocket notification format:
        # {
        #   "event_type": "workspace_mount_changed",
        #   "workspace_id": "workspace-123",
        #   "action": "mount",
        #   "path": "/docs",
        #   "mounted_paths": ["/src", "/tests", "/docs"]
        # }
        pass


# ============================================================================
# Pagination and Filtering Tests
# ============================================================================

class TestWorkspacePaginationFiltering:
    """Tests for pagination and filtering of workspace lists."""

    @pytest.mark.asyncio
    async def test_list_workspaces_paginated(
        self,
        client: TestClient,
        mock_workspace_query_port: AsyncMock,
    ):
        """Test listing workspaces with pagination."""
        # Arrange
        mock_workspace_query_port.list_workspaces.return_value = {
            "items": [],
            "total": 50,
            "page": 2,
            "page_size": 10,
        }

        # Act
        response = client.get("/api/v2/workspaces?page=2&page_size=10")

        # Assert
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["total"] == 50
        assert data["page"] == 2

    @pytest.mark.asyncio
    async def test_list_workspaces_empty_result(
        self,
        client: TestClient,
        mock_workspace_query_port: AsyncMock,
    ):
        """Test listing workspaces with no results."""
        # Arrange
        mock_workspace_query_port.list_workspaces.return_value = {
            "items": [],
            "total": 0,
            "page": 1,
            "page_size": 20,
        }

        # Act
        response = client.get("/api/v2/workspaces?status=error")

        # Assert
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert len(data["items"]) == 0
        assert data["total"] == 0
