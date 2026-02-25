"""Integration tests for Work Items REST API endpoints."""

from datetime import UTC, datetime
from unittest.mock import AsyncMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from codetoreum.adapters.primary.routers.work_items import create_work_items_router
from codetoreum.domain.work_item import WorkItem, WorkItemPriority, WorkItemStatus
from codetoreum.ports.input.work_item_command import (
    CreateWorkItemCommand,
    IWorkItemCommandPort,
    UpdateWorkItemCommand,
    WorkItemCommandResult,
)
from codetoreum.ports.input.work_item_query import (
    IWorkItemQueryPort,
    WorkItemHistory,
    WorkItemListResult,
)


class MockWorkItemCommandPort(IWorkItemCommandPort):
    """Mock implementation of work item command port for testing."""

    def __init__(self):
        self._create_work_item = AsyncMock()
        self._update_work_item = AsyncMock()
        self._delete_work_item = AsyncMock()
        self._assign_agent = AsyncMock()
        self._update_labels = AsyncMock()
        self._update_priority = AsyncMock()
        self._attach_workflow = AsyncMock()
        self._update_stage = AsyncMock()

    async def create_work_item(self, command):
        return await self._create_work_item(command)

    async def update_work_item(self, command):
        return await self._update_work_item(command)

    async def delete_work_item(self, work_item_id):
        return await self._delete_work_item(work_item_id)

    async def assign_agent(self, command):
        return await self._assign_agent(command)

    async def update_labels(self, command):
        return await self._update_labels(command)

    async def update_priority(self, command):
        return await self._update_priority(command)

    async def attach_workflow(self, command):
        return await self._attach_workflow(command)

    async def update_stage(self, command):
        return await self._update_stage(command)


class MockWorkItemQueryPort(IWorkItemQueryPort):
    """Mock implementation of work item query port for testing."""

    def __init__(self):
        self._get_work_item = AsyncMock()
        self._list_work_items = AsyncMock()
        self._search_work_items = AsyncMock()
        self._get_work_item_history = AsyncMock()
        self._count_work_items = AsyncMock()

    async def get_work_item(self, work_item_id):
        return await self._get_work_item(work_item_id)

    async def list_work_items(self, filters=None, pagination=None):
        return await self._list_work_items(filters, pagination)

    async def search_work_items(self, search_params):
        return await self._search_work_items(search_params)

    async def get_work_item_history(self, work_item_id, limit=None):
        return await self._get_work_item_history(work_item_id, limit)

    async def count_work_items(self, filters=None):
        return await self._count_work_items(filters)


@pytest.fixture
def mock_command_port():
    """Fixture providing mock work item command port."""
    return MockWorkItemCommandPort()


@pytest.fixture
def mock_query_port():
    """Fixture providing mock work item query port."""
    return MockWorkItemQueryPort()


@pytest.fixture
def app(mock_command_port, mock_query_port):
    """Fixture providing FastAPI test application."""
    app = FastAPI()

    # Create and include work items router (without auth for testing)
    router = create_work_items_router(
        command_port=mock_command_port,
        query_port=mock_query_port,
        auth_deps=None,  # Disable auth for testing
    )
    app.include_router(router)

    return app


@pytest.fixture
def client(app):
    """Fixture providing test client."""
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def sample_work_item():
    """Fixture providing a sample work item."""
    now = datetime.now(UTC)
    return WorkItem(
        id="wi-123",
        project_id="proj-123",
        title="Test Work Item",
        description="Test description",
        status=WorkItemStatus.IN_PROGRESS,
        priority=WorkItemPriority.HIGH,
        labels=["bug", "urgent"],
        external_id="42",
        external_url="https://github.com/org/repo/issues/42",
        assigned_agent_id="agent-123",
        assigned_at=now,
        current_workflow_id="wf-123",
        current_stage="development",
        created_at=now,
        updated_at=now,
        completed_at=None,
    )


class TestCreateWorkItem:
    """Tests for POST /api/v2/work-items endpoint."""

    def test_create_work_item_success(self, client, mock_command_port, sample_work_item):
        """Test successful work item creation."""
        # Arrange
        mock_command_port._create_work_item.return_value = sample_work_item

        request_data = {
            "project_id": "proj-123",
            "title": "Test Work Item",
            "description": "Test description",
            "labels": ["bug", "urgent"],
            "priority": "HIGH",
            "external_id": "42",
            "external_url": "https://github.com/org/repo/issues/42",
        }

        # Act
        response = client.post("/api/v2/work-items", json=request_data)

        # Assert
        assert response.status_code == 201
        data = response.json()
        assert data["id"] == "wi-123"
        assert data["title"] == "Test Work Item"
        assert data["status"] == "in_progress"
        assert data["priority"] == "HIGH"
        assert data["labels"] == ["bug", "urgent"]

        # Verify command port was called
        mock_command_port._create_work_item.assert_called_once()
        call_args = mock_command_port._create_work_item.call_args[0][0]
        assert isinstance(call_args, CreateWorkItemCommand)
        assert call_args.title == "Test Work Item"

    def test_create_work_item_with_defaults(self, client, mock_command_port, sample_work_item):
        """Test work item creation with default values."""
        # Arrange
        mock_command_port._create_work_item.return_value = sample_work_item

        request_data = {
            "project_id": "proj-123",
            "title": "Test Work Item",
            "description": "Test description",
        }

        # Act
        response = client.post("/api/v2/work-items", json=request_data)

        # Assert
        assert response.status_code == 201
        data = response.json()
        assert data["title"] == "Test Work Item"

    def test_create_work_item_validation_error(self, client):
        """Test work item creation with invalid data."""
        # Arrange
        request_data = {
            "project_id": "",  # Empty project ID
            "title": "",  # Empty title
            "description": "Test description",
        }

        # Act
        response = client.post("/api/v2/work-items", json=request_data)

        # Assert
        assert response.status_code == 422  # Validation error


class TestListWorkItems:
    """Tests for GET /api/v2/work-items endpoint."""

    def test_list_work_items_success(self, client, mock_query_port, sample_work_item):
        """Test successful work items listing."""
        # Arrange
        mock_query_port._list_work_items.return_value = WorkItemListResult(
            work_items=[sample_work_item],
            total_count=1,
            offset=0,
            limit=20,
            has_next=False,
        )

        # Act
        response = client.get("/api/v2/work-items")

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert data["total_count"] == 1
        assert len(data["work_items"]) == 1
        assert data["work_items"][0]["id"] == "wi-123"
        assert data["has_next"] is False

    def test_list_work_items_with_filters(self, client, mock_query_port, sample_work_item):
        """Test work items listing with filters."""
        # Arrange
        mock_query_port._list_work_items.return_value = WorkItemListResult(
            work_items=[sample_work_item],
            total_count=1,
            offset=0,
            limit=20,
            has_next=False,
        )

        # Act
        response = client.get("/api/v2/work-items?status=in_progress&priority=HIGH&labels=bug,urgent")

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert data["total_count"] == 1

        # Verify filters were applied
        mock_query_port._list_work_items.assert_called_once()
        call_args = mock_query_port._list_work_items.call_args[0]
        filters = call_args[0]
        assert filters.status == WorkItemStatus.IN_PROGRESS
        assert filters.priority == WorkItemPriority.HIGH
        assert filters.labels == ["bug", "urgent"]

    def test_list_work_items_with_pagination(self, client, mock_query_port, sample_work_item):
        """Test work items listing with pagination."""
        # Arrange
        mock_query_port._list_work_items.return_value = WorkItemListResult(
            work_items=[sample_work_item],
            total_count=100,
            offset=20,
            limit=50,
            has_next=True,
        )

        # Act
        response = client.get("/api/v2/work-items?offset=20&limit=50")

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert data["total_count"] == 100
        assert data["page"] == 1  # (offset=20 / limit=50) + 1 = 1
        assert data["page_size"] == 50
        assert data["has_next"] is True

    def test_list_work_items_with_search(self, client, mock_query_port, sample_work_item):
        """Test work items listing with search query."""
        # Arrange
        mock_query_port._search_work_items.return_value = WorkItemListResult(
            work_items=[sample_work_item],
            total_count=1,
            offset=0,
            limit=20,
            has_next=False,
        )

        # Act
        response = client.get("/api/v2/work-items?search=authentication")

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert data["total_count"] == 1

        # Verify search was called
        mock_query_port._search_work_items.assert_called_once()


class TestGetWorkItem:
    """Tests for GET /api/v2/work-items/{id} endpoint."""

    def test_get_work_item_success(self, client, mock_query_port, sample_work_item):
        """Test successful work item retrieval."""
        # Arrange
        mock_query_port._get_work_item.return_value = sample_work_item
        mock_query_port._get_work_item_history.return_value = WorkItemHistory(
            work_item=sample_work_item,
            events=[
                {
                    "event_type": "WorkItemCreated",
                    "occurred_at": "2025-11-03T09:00:00Z",
                }
            ],
            total_events=1,
        )

        # Act
        response = client.get("/api/v2/work-items/wi-123")

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert data["id"] == "wi-123"
        assert data["title"] == "Test Work Item"
        assert data["history_event_count"] == 1
        assert len(data["recent_events"]) == 1

    def test_get_work_item_not_found(self, client, mock_query_port):
        """Test work item retrieval when not found."""
        # Arrange
        mock_query_port._get_work_item.side_effect = Exception("Work item not found")

        # Act
        response = client.get("/api/v2/work-items/wi-nonexistent")

        # Assert
        assert response.status_code == 404


class TestUpdateWorkItem:
    """Tests for PUT /api/v2/work-items/{id} endpoint."""

    def test_update_work_item_success(self, client, mock_command_port, sample_work_item):
        """Test successful work item update."""
        # Arrange
        mock_command_port._update_work_item.return_value = sample_work_item

        request_data = {
            "title": "Updated Title",
            "priority": "CRITICAL",
        }

        # Act
        response = client.put("/api/v2/work-items/wi-123", json=request_data)

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert data["id"] == "wi-123"

        # Verify command port was called
        mock_command_port._update_work_item.assert_called_once()
        call_args = mock_command_port._update_work_item.call_args[0][0]
        assert isinstance(call_args, UpdateWorkItemCommand)
        assert call_args.work_item_id == "wi-123"

    def test_update_work_item_not_found(self, client, mock_command_port):
        """Test work item update when not found."""
        # Arrange
        mock_command_port._update_work_item.side_effect = Exception("Work item not found")

        request_data = {
            "title": "Updated Title",
        }

        # Act
        response = client.put("/api/v2/work-items/wi-nonexistent", json=request_data)

        # Assert
        assert response.status_code == 404


class TestDeleteWorkItem:
    """Tests for DELETE /api/v2/work-items/{id} endpoint."""

    def test_delete_work_item_success(self, client, mock_command_port):
        """Test successful work item deletion."""
        # Arrange
        mock_command_port._delete_work_item.return_value = WorkItemCommandResult(
            success=True,
            work_item_id="wi-123",
            message="Work item deleted successfully",
        )

        # Act
        response = client.delete("/api/v2/work-items/wi-123")

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["work_item_id"] == "wi-123"
        assert data["message"] == "Work item deleted successfully"

    def test_delete_work_item_not_found(self, client, mock_command_port):
        """Test work item deletion when not found."""
        # Arrange
        mock_command_port._delete_work_item.side_effect = Exception("Work item not found")

        # Act
        response = client.delete("/api/v2/work-items/wi-nonexistent")

        # Assert
        assert response.status_code == 404
