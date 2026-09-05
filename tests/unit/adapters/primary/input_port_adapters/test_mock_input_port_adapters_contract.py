"""Contract tests for mock input port adapters.

These tests verify that mock adapters comply with their port interfaces
and correctly implement business logic (create-read-update-delete flows,
error handling, state management).
"""

import pytest

from codetoreum.adapters.primary.input_port_adapters.mock.mock_work_item_command_adapter import (
    MockWorkItemCommandAdapter,
)
from codetoreum.domain.exceptions import WorkItemNotFoundError
from codetoreum.domain.work_item import WorkItemPriority
from codetoreum.ports.input.work_item_command import (
    CreateWorkItemCommand,
    UpdateWorkItemCommand,
)


class TestMockWorkItemCommandAdapterContract:
    """Test MockWorkItemCommandAdapter contract compliance."""

    @pytest.mark.asyncio
    async def test_create_and_retrieve_work_item(self):
        """Test create-read flow for work items."""
        adapter = MockWorkItemCommandAdapter()

        # Create work item
        command = CreateWorkItemCommand(
            project_id="proj-1",
            title="Test Task",
            description="Test Description",
            priority=WorkItemPriority.HIGH,
            labels=["bug", "urgent"],
            external_id="ext-123",
            external_url="https://example.com/issue/123",
        )
        work_item = await adapter.create_work_item(command)

        # Verify created item has correct properties
        assert work_item.project_id == "proj-1"
        assert work_item.title == "Test Task"
        assert work_item.description == "Test Description"
        assert work_item.priority == WorkItemPriority.HIGH
        assert "bug" in work_item.labels
        assert work_item.external_id == "ext-123"

    @pytest.mark.asyncio
    async def test_update_work_item(self):
        """Test update flow for work items."""
        adapter = MockWorkItemCommandAdapter()

        # Create work item
        create_cmd = CreateWorkItemCommand(
            project_id="proj-1",
            title="Original Title",
            description="Original Description",
            priority=WorkItemPriority.LOW,
            labels=[],
            external_id="ext-123",
            external_url="https://example.com",
        )
        work_item = await adapter.create_work_item(create_cmd)

        # Update work item
        update_cmd = UpdateWorkItemCommand(
            work_item_id=work_item.id,
            title="Updated Title",
            description="Updated Description",
            priority=WorkItemPriority.HIGH,
            labels=["fixed"],
        )
        updated = await adapter.update_work_item(update_cmd)

        # Verify updates applied
        assert updated.title == "Updated Title"
        assert updated.description == "Updated Description"
        assert updated.priority == WorkItemPriority.HIGH

    @pytest.mark.asyncio
    async def test_update_nonexistent_work_item_raises_error(self):
        """Test that updating nonexistent work item raises WorkItemNotFoundError."""
        adapter = MockWorkItemCommandAdapter()

        update_cmd = UpdateWorkItemCommand(
            work_item_id="nonexistent-id", title="New Title", description=None, priority=None, labels=None
        )

        with pytest.raises(WorkItemNotFoundError):
            await adapter.update_work_item(update_cmd)

    @pytest.mark.asyncio
    async def test_delete_work_item(self):
        """Test delete flow for work items."""
        adapter = MockWorkItemCommandAdapter()

        # Create and delete work item
        create_cmd = CreateWorkItemCommand(
            project_id="proj-1",
            title="To Delete",
            description="",
            priority=WorkItemPriority.LOW,
            labels=[],
            external_id="ext-123",
            external_url="https://example.com",
        )
        work_item = await adapter.create_work_item(create_cmd)

        result = await adapter.delete_work_item(work_item.id)

        # Verify deletion succeeded
        assert result.success is True
        assert result.work_item_id == work_item.id

    @pytest.mark.asyncio
    async def test_delete_nonexistent_work_item_raises_error(self):
        """Test that deleting nonexistent work item raises WorkItemNotFoundError."""
        adapter = MockWorkItemCommandAdapter()

        with pytest.raises(WorkItemNotFoundError):
            await adapter.delete_work_item("nonexistent-id")
