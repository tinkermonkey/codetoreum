"""Contract tests for IWorkItemService interface.

These abstract tests verify that all IWorkItemService implementations
follow the contract correctly, including event emission on creation/updates
and monitoring lifecycle support.
"""

from abc import ABC, abstractmethod
from datetime import datetime
from typing import List

import pytest

from codetoreum.domain.types import ProjectId, WorkItemId
from codetoreum.domain.work_item import WorkItem, WorkItemPriority, WorkItemStatus
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

    # Query Operation Tests

    @pytest.mark.asyncio
    async def test_get_work_item_returns_work_item(self):
        """Should return a work item by ID."""
        service = await self.create_service()

        # Create a work item first
        item = await service.create_work_item(
            project_id=ProjectId("proj-123"), title="Test Item", description="Test Description"
        )

        # Retrieve it
        retrieved = await service.get_work_item(WorkItemId(item.id))

        assert isinstance(retrieved, WorkItem)
        assert retrieved.id == item.id
        assert retrieved.title == "Test Item"

    @pytest.mark.asyncio
    async def test_get_work_items_by_status_returns_list(self):
        """Should return list of work items filtered by status."""
        service = await self.create_service()

        items = await service.get_work_items_by_status(ProjectId("proj-123"), "open")

        assert isinstance(items, list)
        for item in items:
            assert isinstance(item, WorkItem)

    @pytest.mark.asyncio
    async def test_get_work_items_by_column_returns_list(self):
        """Should return list of work items in a column."""
        service = await self.create_service()

        items = await service.get_work_items_by_column(ProjectId("proj-123"), "Backlog")

        assert isinstance(items, list)
        for item in items:
            assert isinstance(item, WorkItem)

    # Command Operation Tests

    @pytest.mark.asyncio
    async def test_create_work_item_emits_event(self):
        """Creating a work item should emit workitem.created event."""
        service = await self.create_service()

        events: list = []
        service.on("workitem.created", lambda e: events.append(e))

        item = await service.create_work_item(
            project_id=ProjectId("proj-123"), title="New Item", description="Description"
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
            project_id=ProjectId("proj-123"), title="Original Title", description="Original Description"
        )

        # Setup event capture
        events: list = []
        service.on("workitem.updated", lambda e: events.append(e))

        # Update it
        updated = await service.update_work_item(WorkItemId(item.id), {"title": "Updated Title"})

        assert isinstance(updated, WorkItem)
        assert updated.title == "Updated Title"
        # Should have emitted at least one event
        assert len(events) > 0

    # Monitoring Lifecycle Tests

    @pytest.mark.asyncio
    async def test_monitoring_lifecycle(self):
        """Should support start/stop monitoring for work item changes."""
        service = await self.create_service()
        config = MonitoringConfig(project_id=ProjectId("proj-123"))

        # Start monitoring
        await service.start_monitoring(ProjectId("proj-123"), config)
        status = await service.get_monitoring_status(ProjectId("proj-123"))
        assert status.state.value == "active"

        # Stop monitoring
        await service.stop_monitoring(ProjectId("proj-123"))
        status = await service.get_monitoring_status(ProjectId("proj-123"))
        assert status.state.value == "stopped"

    @pytest.mark.asyncio
    async def test_work_item_has_required_fields(self):
        """WorkItem should have all required fields."""
        service = await self.create_service()

        item = await service.create_work_item(
            project_id=ProjectId("proj-123"), title="Test Item", description="Test Description"
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
        assert isinstance(item.status, WorkItemStatus)
        assert isinstance(item.created_at, datetime)
        assert isinstance(item.updated_at, datetime)

    @pytest.mark.asyncio
    async def test_multiple_projects_independent(self):
        """Work items should be independent per project."""
        service = await self.create_service()
        config1 = MonitoringConfig(project_id=ProjectId("proj-1"))
        config2 = MonitoringConfig(project_id=ProjectId("proj-2"))

        await service.start_monitoring(ProjectId("proj-1"), config1)
        await service.start_monitoring(ProjectId("proj-2"), config2)

        # Both should be active
        status1 = await service.get_monitoring_status(ProjectId("proj-1"))
        status2 = await service.get_monitoring_status(ProjectId("proj-2"))

        assert status1.state.value == "active"
        assert status2.state.value == "active"

        # Stop one shouldn't affect the other
        await service.stop_monitoring(ProjectId("proj-1"))

        status1 = await service.get_monitoring_status(ProjectId("proj-1"))
        status2 = await service.get_monitoring_status(ProjectId("proj-2"))

        assert status1.state.value == "stopped"
        assert status2.state.value == "active"

    @pytest.mark.asyncio
    async def test_work_item_update_returns_updated_state(self):
        """Update should return the updated work item state."""
        service = await self.create_service()

        item = await service.create_work_item(project_id=ProjectId("proj-123"), title="Original", description="Desc")

        updated = await service.update_work_item(
            WorkItemId(item.id), {"title": "Updated Title", "status": "in_progress"}
        )

        assert updated.title == "Updated Title"
        assert updated.status == WorkItemStatus.IN_PROGRESS
        assert updated.id == item.id  # Same item

    # Negative Test Cases

    @pytest.mark.asyncio
    async def test_empty_string_title_validation(self):
        """Test that empty string in required title field raises ValidationError."""
        service = await self.create_service()

        with pytest.raises((ValueError, AttributeError, TypeError)):
            await service.create_work_item(
                project_id=ProjectId("proj-123"),
                title="",  # Empty string - should fail
                description="Test Description",
            )

    @pytest.mark.asyncio
    async def test_empty_string_project_id_validation(self):
        """Test that empty string in project_id raises ValidationError."""
        service = await self.create_service()

        with pytest.raises((ValueError, AttributeError, TypeError)):
            await service.create_work_item(
                project_id=ProjectId(""),  # Empty - should fail
                title="Test Title",
                description="Test Description",
            )

    @pytest.mark.asyncio
    async def test_sql_injection_pattern_in_id(self):
        """Test that SQL injection patterns in work item ID are rejected."""
        service = await self.create_service()

        # Create a valid item first
        item = await service.create_work_item(project_id=ProjectId("proj-123"), title="Test", description="Test")

        # Attempt to get with malicious ID
        with pytest.raises((ValueError, KeyError)):
            await service.get_work_item(WorkItemId("'; DROP TABLE items; --"))

    @pytest.mark.asyncio
    async def test_xss_pattern_in_title(self):
        """Test that XSS patterns in title field are handled safely."""
        service = await self.create_service()

        # Should either reject or sanitize
        try:
            item = await service.create_work_item(
                project_id=ProjectId("proj-123"), title="<script>alert('XSS')</script>", description="Test"
            )
            # If it passes, raw script tags must not appear in output
            assert "<script>" not in item.title
        except (ValueError, TypeError):
            # Rejection is also acceptable
            pass

    @pytest.mark.asyncio
    async def test_oversized_description_rejected(self):
        """Test that oversized input is rejected."""
        service = await self.create_service()

        # Create a 10MB description
        huge_description = "x" * (10 * 1024 * 1024)

        with pytest.raises((ValueError, MemoryError, AttributeError)):
            await service.create_work_item(project_id=ProjectId("proj-123"), title="Test", description=huge_description)

    @pytest.mark.asyncio
    async def test_invalid_enum_value_rejected(self):
        """Test that invalid enum values are rejected."""
        service = await self.create_service()

        item = await service.create_work_item(project_id=ProjectId("proj-123"), title="Test", description="Test")

        # Attempt to set invalid status
        with pytest.raises((ValueError, KeyError)):
            await service.update_work_item(WorkItemId(item.id), {"status": "INVALID_STATUS_12345"})

    @pytest.mark.asyncio
    async def test_nonexistent_item_not_found(self):
        """Test that querying nonexistent item raises appropriate error."""
        service = await self.create_service()

        with pytest.raises((ValueError, KeyError)):
            await service.get_work_item(WorkItemId("nonexistent-id-12345"))

    # Boundary Value Tests

    @pytest.mark.asyncio
    async def test_priority_minimum_boundary(self):
        """Test that priority field accepts minimum valid value (1)."""
        service = await self.create_service()

        item = await service.create_work_item(
            project_id=ProjectId("proj-123"), title="Test Item", description="Test Description"
        )

        # Update to minimum valid priority (1 = LOW)
        updated = await service.update_work_item(WorkItemId(item.id), {"priority": 1})
        assert updated.priority == WorkItemPriority.LOW

    @pytest.mark.asyncio
    async def test_priority_maximum_boundary(self):
        """Test that priority field accepts maximum valid value (4)."""
        service = await self.create_service()

        item = await service.create_work_item(
            project_id=ProjectId("proj-123"), title="Test Item", description="Test Description"
        )

        # Update to maximum valid priority (4 = CRITICAL)
        updated = await service.update_work_item(WorkItemId(item.id), {"priority": 4})
        assert updated.priority == WorkItemPriority.CRITICAL

    @pytest.mark.asyncio
    async def test_priority_zero_rejected(self):
        """Test that priority value of zero is rejected as invalid."""
        service = await self.create_service()

        item = await service.create_work_item(
            project_id=ProjectId("proj-123"), title="Test Item", description="Test Description"
        )

        # Zero priority should fail
        with pytest.raises((ValueError, KeyError)):
            await service.update_work_item(WorkItemId(item.id), {"priority": 0})

    @pytest.mark.asyncio
    async def test_priority_negative_rejected(self):
        """Test that negative priority values are rejected."""
        service = await self.create_service()

        item = await service.create_work_item(
            project_id=ProjectId("proj-123"), title="Test Item", description="Test Description"
        )

        # Negative priority should fail
        with pytest.raises((ValueError, KeyError)):
            await service.update_work_item(WorkItemId(item.id), {"priority": -1})

    @pytest.mark.asyncio
    async def test_priority_excessive_rejected(self):
        """Test that priority values exceeding maximum are rejected."""
        service = await self.create_service()

        item = await service.create_work_item(
            project_id=ProjectId("proj-123"), title="Test Item", description="Test Description"
        )

        # Priority > 4 should fail
        with pytest.raises((ValueError, KeyError)):
            await service.update_work_item(WorkItemId(item.id), {"priority": 5})

    @pytest.mark.asyncio
    async def test_title_at_maximum_length(self):
        """Test that title field accepts string at maximum length boundary (255 chars)."""
        service = await self.create_service()

        # Create title exactly at 255 character boundary
        max_title = "x" * 255
        item = await service.create_work_item(
            project_id=ProjectId("proj-123"), title=max_title, description="Test Description"
        )

        assert len(item.title) == 255
        assert item.title == max_title

    @pytest.mark.asyncio
    async def test_title_exceeds_maximum_length_rejected(self):
        """Test that title exceeding maximum length is rejected."""
        service = await self.create_service()

        # Create title exceeding 255 character boundary
        oversized_title = "x" * 256

        with pytest.raises((ValueError, AttributeError)):
            await service.create_work_item(
                project_id=ProjectId("proj-123"), title=oversized_title, description="Test Description"
            )

    @pytest.mark.asyncio
    async def test_description_with_boundary_length(self):
        """Test that description field handles reasonable length boundaries."""
        service = await self.create_service()

        # Create description at a reasonable boundary (e.g., 1000 chars)
        long_description = "y" * 1000
        item = await service.create_work_item(
            project_id=ProjectId("proj-123"), title="Test Item", description=long_description
        )

        assert len(item.description) == 1000

    @pytest.mark.asyncio
    async def test_emoji_in_title(self):
        """Test that emoji characters in title are handled correctly."""
        service = await self.create_service()

        item = await service.create_work_item(
            project_id=ProjectId("proj-123"), title="Fix bug 🐛 in login", description="Test Description"
        )

        assert "🐛" in item.title
        assert "Fix bug" in item.title

    @pytest.mark.asyncio
    async def test_emoji_in_description(self):
        """Test that emoji characters in description are handled correctly."""
        service = await self.create_service()

        item = await service.create_work_item(
            project_id=ProjectId("proj-123"), title="Test Item", description="Deploy to production 🚀 ASAP ⚡"
        )

        assert "🚀" in item.description
        assert "⚡" in item.description

    @pytest.mark.asyncio
    async def test_rtl_text_in_title(self):
        """Test that right-to-left (RTL) text in title is handled correctly."""
        service = await self.create_service()

        item = await service.create_work_item(
            project_id=ProjectId("proj-123"),
            title="مرحبا بك Test",  # Arabic + English
            description="Test Description",
        )

        assert "مرحبا" in item.title
        assert "Test" in item.title

    @pytest.mark.asyncio
    async def test_rtl_text_in_description(self):
        """Test that right-to-left (RTL) text in description is handled correctly."""
        service = await self.create_service()

        item = await service.create_work_item(
            project_id=ProjectId("proj-123"), title="Test Item", description="مرحبا بك في النظام Test description"
        )

        assert "مرحبا" in item.description

    @pytest.mark.asyncio
    async def test_combining_characters_in_title(self):
        """Test that combining characters (accents) in title are preserved."""
        service = await self.create_service()

        item = await service.create_work_item(
            project_id=ProjectId("proj-123"), title="Café résumé", description="Test Description"
        )

        assert "Café" in item.title
        assert "résumé" in item.title

    @pytest.mark.asyncio
    async def test_combining_characters_in_description(self):
        """Test that combining characters (accents) in description are preserved."""
        service = await self.create_service()

        item = await service.create_work_item(
            project_id=ProjectId("proj-123"), title="Test Item", description="Implement naïve algorithm for Zürich café"
        )

        assert "naïve" in item.description
        assert "Zürich" in item.description

    @pytest.mark.asyncio
    async def test_zero_width_characters_in_title(self):
        """Test that zero-width characters in title are handled appropriately."""
        service = await self.create_service()

        # Zero-width space: U+200B
        item = await service.create_work_item(
            project_id=ProjectId("proj-123"), title="Test\u200bwith\u200bzero-width", description="Test Description"
        )

        # Item should be created (handling could be preservation or stripping)
        assert "Test" in item.title

    @pytest.mark.asyncio
    async def test_zero_width_characters_in_description(self):
        """Test that zero-width characters in description are handled appropriately."""
        service = await self.create_service()

        # Zero-width space: U+200B
        item = await service.create_work_item(
            project_id=ProjectId("proj-123"), title="Test Item", description="Description\u200bwith\u200bzero-width"
        )

        # Item should be created (handling could be preservation or stripping)
        assert "Description" in item.description

    @pytest.mark.asyncio
    async def test_null_byte_in_title_rejected(self):
        """Test that null bytes in title are rejected or sanitized."""
        service = await self.create_service()

        # Null byte: U+0000
        try:
            item = await service.create_work_item(
                project_id=ProjectId("proj-123"), title="Test\x00Null", description="Test Description"
            )
            # If accepted, verify null byte is not preserved as-is
            assert "\x00" not in item.title
        except (ValueError, AttributeError):
            # Rejection is acceptable
            pass

    @pytest.mark.asyncio
    async def test_null_byte_in_description_rejected(self):
        """Test that null bytes in description are rejected or sanitized."""
        service = await self.create_service()

        # Null byte: U+0000
        try:
            item = await service.create_work_item(
                project_id=ProjectId("proj-123"), title="Test Item", description="Description\x00Null"
            )
            # If accepted, verify null byte is not preserved as-is
            assert "\x00" not in item.description
        except (ValueError, AttributeError):
            # Rejection is acceptable
            pass
