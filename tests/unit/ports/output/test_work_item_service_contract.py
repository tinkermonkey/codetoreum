"""Contract tests for IWorkItemService interface.

These abstract tests verify that all IWorkItemService implementations
follow the contract correctly, including event emission on creation/updates
and monitoring lifecycle support.
"""

from abc import ABC, abstractmethod
from typing import List

import pytest

from codetoreum.domain.work_item import WorkItem
from codetoreum.ports.output.monitoring import MonitoringConfig
from codetoreum.ports.output.work_item_service import IWorkItemService


class TestWorkItemServiceContract(ABC):
    """Abstract contract tests for IWorkItemService implementations.

    Subclasses must implement create_service() to provide a concrete
    IWorkItemService implementation to test.
    """

    @abstractmethod
    async def create_service(self) -> IWorkItemService:
        """Create and return an IWorkItemService instance for testing."""
        pass

    # Query Operation Tests

    @pytest.mark.asyncio
    async def test_get_work_item_returns_work_item(self):
        """Should return a work item by ID."""
        service = await self.create_service()

        # Create a work item first
        item = await service.create_work_item(
            project_id="proj-123",
            title="Test Item",
            description="Test Description"
        )

        # Retrieve it
        retrieved = await service.get_work_item(item.id)

        assert isinstance(retrieved, WorkItem)
        assert retrieved.id == item.id
        assert retrieved.title == "Test Item"

    @pytest.mark.asyncio
    async def test_get_work_items_by_status_returns_list(self):
        """Should return list of work items filtered by status."""
        service = await self.create_service()

        items = await service.get_work_items_by_status("proj-123", "open")

        assert isinstance(items, list)
        for item in items:
            assert isinstance(item, WorkItem)

    @pytest.mark.asyncio
    async def test_get_work_items_by_column_returns_list(self):
        """Should return list of work items in a column."""
        service = await self.create_service()

        items = await service.get_work_items_by_column("proj-123", "Backlog")

        assert isinstance(items, list)
        for item in items:
            assert isinstance(item, WorkItem)

    # Command Operation Tests

    @pytest.mark.asyncio
    async def test_create_work_item_emits_event(self):
        """Creating a work item should emit workitem.created event."""
        service = await self.create_service()

        events: List = []
        service.on("workitem.created", lambda e: events.append(e))

        item = await service.create_work_item(
            project_id="proj-123",
            title="New Item",
            description="Description"
        )

        assert isinstance(item, WorkItem)
        # Should have emitted at least one event
        assert len(events) > 0

    @pytest.mark.asyncio
    async def test_update_work_item_emits_event(self):
        """Updating a work item should emit workitem.updated event."""
        service = await self.create_service()

        # Create item
        item = await service.create_work_item(
            project_id="proj-123",
            title="Original Title",
            description="Original Description"
        )

        # Setup event capture
        events: List = []
        service.on("workitem.updated", lambda e: events.append(e))

        # Update it
        updated = await service.update_work_item(
            item.id,
            {"title": "Updated Title"}
        )

        assert isinstance(updated, WorkItem)
        assert updated.title == "Updated Title"
        # Should have emitted at least one event
        assert len(events) > 0

    # Monitoring Lifecycle Tests

    @pytest.mark.asyncio
    async def test_monitoring_lifecycle(self):
        """Should support start/stop monitoring for work item changes."""
        service = await self.create_service()
        config = MonitoringConfig(project_id="proj-123")

        # Start monitoring
        await service.start_monitoring("proj-123", config)
        status = await service.get_monitoring_status("proj-123")
        assert status.state.value == "active"

        # Stop monitoring
        await service.stop_monitoring("proj-123")
        status = await service.get_monitoring_status("proj-123")
        assert status.state.value == "stopped"

    @pytest.mark.asyncio
    async def test_work_item_has_required_fields(self):
        """WorkItem should have all required fields."""
        service = await self.create_service()

        item = await service.create_work_item(
            project_id="proj-123",
            title="Test Item",
            description="Test Description"
        )

        # Check required fields
        assert hasattr(item, "id")
        assert hasattr(item, "title")
        assert hasattr(item, "description")
        assert hasattr(item, "status")
        assert hasattr(item, "created_at")
        assert hasattr(item, "updated_at")

        assert isinstance(item.id, str)
        assert isinstance(item.title, str)
        assert isinstance(item.description, str)
        assert isinstance(item.status, str)
        assert isinstance(item.created_at, str)
        assert isinstance(item.updated_at, str)

    @pytest.mark.asyncio
    async def test_multiple_projects_independent(self):
        """Work items should be independent per project."""
        service = await self.create_service()
        config1 = MonitoringConfig(project_id="proj-1")
        config2 = MonitoringConfig(project_id="proj-2")

        await service.start_monitoring("proj-1", config1)
        await service.start_monitoring("proj-2", config2)

        # Both should be active
        status1 = await service.get_monitoring_status("proj-1")
        status2 = await service.get_monitoring_status("proj-2")

        assert status1.state.value == "active"
        assert status2.state.value == "active"

        # Stop one shouldn't affect the other
        await service.stop_monitoring("proj-1")

        status1 = await service.get_monitoring_status("proj-1")
        status2 = await service.get_monitoring_status("proj-2")

        assert status1.state.value == "stopped"
        assert status2.state.value == "active"

    @pytest.mark.asyncio
    async def test_work_item_update_returns_updated_state(self):
        """Update should return the updated work item state."""
        service = await self.create_service()

        item = await service.create_work_item(
            project_id="proj-123",
            title="Original",
            description="Desc"
        )

        updated = await service.update_work_item(
            item.id,
            {
                "title": "Updated Title",
                "status": "in_progress"
            }
        )

        assert updated.title == "Updated Title"
        assert updated.status == "in_progress"
        assert updated.id == item.id  # Same item
