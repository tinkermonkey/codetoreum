"""Unit tests for Work Item DTO mappers."""

from datetime import UTC, datetime

from codetoreum.adapters.primary.work_item_dtos import (
    CreateWorkItemRequest,
    UpdateWorkItemRequest,
)
from codetoreum.adapters.primary.work_item_mappers import WorkItemMapper
from codetoreum.domain.work_item import WorkItem, WorkItemPriority, WorkItemStatus
from codetoreum.ports.input.work_item_command import (
    WorkItemCommandResult as DomainCommandResult,
)
from codetoreum.ports.input.work_item_query import (
    WorkItemHistory,
    WorkItemListResult,
)


class TestWorkItemMapper:
    """Test suite for WorkItemMapper."""

    def test_to_create_command_with_defaults(self):
        """Test converting CreateWorkItemRequest with default values."""
        # Arrange
        dto = CreateWorkItemRequest(
            project_id="proj-123",
            title="Test Work Item",
            description="Test description",
            labels=None,
            priority="MEDIUM",
            external_id=None,
            external_url=None,
        )

        # Act
        command = WorkItemMapper.to_create_command(dto)

        # Assert
        assert command.project_id == "proj-123"
        assert command.title == "Test Work Item"
        assert command.description == "Test description"
        assert command.labels is None
        assert command.priority == WorkItemPriority.MEDIUM
        assert command.external_id is None
        assert command.external_url is None

    def test_to_update_command_partial(self):
        """Test converting UpdateWorkItemRequest with partial updates."""
        # Arrange
        dto = UpdateWorkItemRequest(
            title="Updated Title",
            description=None,
            labels=None,
            priority=None,
        )

        # Act
        command = WorkItemMapper.to_update_command("wi-123", dto)

        # Assert
        assert command.work_item_id == "wi-123"
        assert command.title == "Updated Title"
        assert command.description is None
        assert command.labels is None
        assert command.priority is None

    def test_to_response(self):
        """Test converting WorkItem domain model to WorkItemResponse DTO."""
        # Arrange
        now = datetime.now(UTC)
        work_item = WorkItem(
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

        # Act
        response = WorkItemMapper.to_response(work_item)

        # Assert
        assert response.id == "wi-123"
        assert response.project_id == "proj-123"
        assert response.title == "Test Work Item"
        assert response.description == "Test description"
        assert response.status == "in_progress"
        assert response.priority == "HIGH"
        assert response.labels == ["bug", "urgent"]
        assert response.external_id == "42"
        assert response.external_url == "https://github.com/org/repo/issues/42"
        assert response.assigned_agent_id == "agent-123"
        assert response.assigned_at == now
        assert response.current_workflow_id == "wf-123"
        assert response.current_stage == "development"
        assert response.created_at == now
        assert response.updated_at == now
        assert response.completed_at is None

    def test_to_response_does_not_mutate_labels(self):
        """Test that to_response copies labels to prevent mutation."""
        # Arrange
        now = datetime.now(UTC)
        work_item = WorkItem(
            id="wi-123",
            project_id="proj-123",
            title="Test Work Item",
            description="Test description",
            status=WorkItemStatus.IN_PROGRESS,
            priority=WorkItemPriority.HIGH,
            labels=["bug", "urgent"],
            external_id=None,
            external_url=None,
            assigned_agent_id=None,
            assigned_at=None,
            current_workflow_id=None,
            current_stage=None,
            created_at=now,
            updated_at=now,
            completed_at=None,
        )

        # Act
        response = WorkItemMapper.to_response(work_item)
        response.labels.append("modified")

        # Assert - original work item labels should not be modified
        assert work_item.labels == ["bug", "urgent"]
        assert response.labels == ["bug", "urgent", "modified"]

    def test_to_detail_response(self):
        """Test converting WorkItem and history to WorkItemDetailResponse."""
        # Arrange
        now = datetime.now(UTC)
        work_item = WorkItem(
            id="wi-123",
            project_id="proj-123",
            title="Test Work Item",
            description="Test description",
            status=WorkItemStatus.IN_PROGRESS,
            priority=WorkItemPriority.HIGH,
            labels=["bug"],
            external_id=None,
            external_url=None,
            assigned_agent_id=None,
            assigned_at=None,
            current_workflow_id=None,
            current_stage=None,
            created_at=now,
            updated_at=now,
            completed_at=None,
        )

        events = [
            {"event_type": "WorkItemCreated", "occurred_at": now.isoformat()},
            {"event_type": "WorkItemStarted", "occurred_at": now.isoformat()},
        ]

        history = WorkItemHistory(
            work_item=work_item,
            events=events,
            total_events=2,
        )

        # Act
        response = WorkItemMapper.to_detail_response(work_item, history)

        # Assert
        assert response.id == "wi-123"
        assert response.title == "Test Work Item"
        assert response.history_event_count == 2
        assert response.recent_events == events

    def test_to_detail_response_limits_recent_events(self):
        """Test that to_detail_response limits recent events to 10."""
        # Arrange
        now = datetime.now(UTC)
        work_item = WorkItem(
            id="wi-123",
            project_id="proj-123",
            title="Test Work Item",
            description="Test description",
            status=WorkItemStatus.IN_PROGRESS,
            priority=WorkItemPriority.HIGH,
            labels=[],
            external_id=None,
            external_url=None,
            assigned_agent_id=None,
            assigned_at=None,
            current_workflow_id=None,
            current_stage=None,
            created_at=now,
            updated_at=now,
            completed_at=None,
        )

        # Create 15 events
        events = [
            {"event_type": f"Event{i}", "occurred_at": now.isoformat()}
            for i in range(15)
        ]

        history = WorkItemHistory(
            work_item=work_item,
            events=events,
            total_events=15,
        )

        # Act
        response = WorkItemMapper.to_detail_response(work_item, history)

        # Assert
        assert response.history_event_count == 15
        assert len(response.recent_events) == 10

    def test_to_list_response(self):
        """Test converting WorkItemListResult to WorkItemListResponse."""
        # Arrange
        now = datetime.now(UTC)
        work_items = [
            WorkItem(
                id="wi-1",
                project_id="proj-123",
                title="Work Item 1",
                description="Description 1",
                status=WorkItemStatus.NEW,
                priority=WorkItemPriority.LOW,
                labels=[],
                external_id=None,
                external_url=None,
                assigned_agent_id=None,
                assigned_at=None,
                current_workflow_id=None,
                current_stage=None,
                created_at=now,
                updated_at=now,
                completed_at=None,
            ),
            WorkItem(
                id="wi-2",
                project_id="proj-123",
                title="Work Item 2",
                description="Description 2",
                status=WorkItemStatus.IN_PROGRESS,
                priority=WorkItemPriority.HIGH,
                labels=["urgent"],
                external_id=None,
                external_url=None,
                assigned_agent_id="agent-123",
                assigned_at=now,
                current_workflow_id=None,
                current_stage=None,
                created_at=now,
                updated_at=now,
                completed_at=None,
            ),
        ]

        result = WorkItemListResult(
            work_items=work_items,
            total_count=2,
            offset=0,
            limit=20,
            has_next=False,
        )

        # Act
        response = WorkItemMapper.to_list_response(result)

        # Assert
        assert len(response.work_items) == 2
        assert response.work_items[0].id == "wi-1"
        assert response.work_items[1].id == "wi-2"
        assert response.total_count == 2
        assert response.page_size == 20
        assert response.has_next is False

    def test_to_command_result(self):
        """Test converting domain command result to API command result."""
        # Arrange
        domain_result = DomainCommandResult(
            success=True,
            work_item_id="wi-123",
            message="Work item deleted successfully",
            errors=None,
        )

        # Act
        response = WorkItemMapper.to_command_result(domain_result)

        # Assert
        assert response.success is True
        assert response.work_item_id == "wi-123"
        assert response.message == "Work item deleted successfully"
        assert response.errors is None

    def test_to_command_result_with_errors(self):
        """Test converting domain command result with errors."""
        # Arrange
        domain_result = DomainCommandResult(
            success=False,
            work_item_id="wi-123",
            message="Operation failed",
            errors=["Error 1", "Error 2"],
        )

        # Act
        response = WorkItemMapper.to_command_result(domain_result)

        # Assert
        assert response.success is False
        assert response.work_item_id == "wi-123"
        assert response.message == "Operation failed"
        assert response.errors == ["Error 1", "Error 2"]
