"""Integration tests for WorkItemService."""

import logging
from datetime import UTC, datetime, timedelta
from typing import Iterator

import pytest

from codetoreum.adapters.testing.in_memory_event_store import InMemoryEventStore
from codetoreum.application.work_item_service import (
    WorkItemNotFoundError,
    WorkItemService,
)
from codetoreum.domain.work_item import (
    WorkItem,
    WorkItemPriority,
    WorkItemStatus,
)
from codetoreum.ports.input.work_item_command import (
    AssignAgentCommand,
    AttachWorkflowCommand,
    CreateWorkItemCommand,
    UpdateLabelsCommand,
    UpdatePriorityCommand,
    UpdateStageCommand,
    UpdateWorkItemCommand,
)
from codetoreum.ports.input.work_item_query import (
    PaginationParams,
    SortField,
    SortOrder,
    WorkItemFilters,
    WorkItemSearchParams,
)


# Fixtures


@pytest.fixture
def event_store() -> Iterator[InMemoryEventStore]:
    """Create in-memory event store."""
    store = InMemoryEventStore()
    yield store
    store.clear()


@pytest.fixture
def work_item_service(event_store: InMemoryEventStore) -> WorkItemService:
    """Create WorkItemService instance."""
    return WorkItemService(event_store=event_store)


# Tests - Create Operations


@pytest.mark.asyncio
async def test_create_work_item(work_item_service: WorkItemService, event_store: InMemoryEventStore):
    """Test creating a new work item."""
    command = CreateWorkItemCommand(
        title="Test Issue",
        description="This is a test issue",
        project_id="project-123",
        labels=["bug", "critical"],
        priority=WorkItemPriority.HIGH,
    )

    work_item = await work_item_service.create_work_item(command)

    assert work_item.id is not None
    assert work_item.title == "Test Issue"
    assert work_item.description == "This is a test issue"
    assert work_item.project_id == "project-123"
    assert work_item.labels == ["bug", "critical"]
    assert work_item.priority == WorkItemPriority.HIGH
    assert work_item.status == WorkItemStatus.NEW
    assert event_store.get_total_event_count() > 0


@pytest.mark.asyncio
async def test_create_work_item_with_external_id(work_item_service: WorkItemService):
    """Test creating work item with external ID."""
    command = CreateWorkItemCommand(
        title="GitHub Issue",
        description="Synced from GitHub",
        project_id="project-123",
        external_id="github-123",
        external_url="https://github.com/test/repo/issues/123",
    )

    work_item = await work_item_service.create_work_item(command)

    assert work_item.external_id == "github-123"
    assert work_item.external_url == "https://github.com/test/repo/issues/123"


# Tests - Read Operations


@pytest.mark.asyncio
async def test_get_work_item(work_item_service: WorkItemService):
    """Test retrieving a work item by ID."""
    # Create work item
    command = CreateWorkItemCommand(
        title="Test Issue",
        description="Description",
        project_id="project-123",
    )
    created = await work_item_service.create_work_item(command)

    # Retrieve work item
    retrieved = await work_item_service.get_work_item(created.id)

    assert retrieved.id == created.id
    assert retrieved.title == "Test Issue"
    assert retrieved.description == "Description"


@pytest.mark.asyncio
async def test_get_nonexistent_work_item(work_item_service: WorkItemService):
    """Test retrieving non-existent work item raises error."""
    with pytest.raises(WorkItemNotFoundError):
        await work_item_service.get_work_item("nonexistent-id")


@pytest.mark.asyncio
async def test_list_work_items_empty(work_item_service: WorkItemService):
    """Test listing work items when none exist."""
    result = await work_item_service.list_work_items()

    assert result.work_items == []
    assert result.total_count == 0
    assert result.has_next is False


@pytest.mark.asyncio
async def test_list_work_items_multiple(work_item_service: WorkItemService):
    """Test listing multiple work items."""
    # Create multiple work items
    for i in range(3):
        command = CreateWorkItemCommand(
            title=f"Issue {i}",
            description=f"Description {i}",
            project_id="project-123",
        )
        await work_item_service.create_work_item(command)

    result = await work_item_service.list_work_items()

    assert len(result.work_items) == 3
    assert result.total_count == 3
    assert result.has_next is False


@pytest.mark.asyncio
async def test_list_work_items_with_pagination(work_item_service: WorkItemService):
    """Test list with pagination."""
    # Create 5 work items
    for i in range(5):
        command = CreateWorkItemCommand(
            title=f"Issue {i}",
            description=f"Description {i}",
            project_id="project-123",
        )
        await work_item_service.create_work_item(command)

    # Get first page (limit 2)
    pagination = PaginationParams(offset=0, limit=2)
    result = await work_item_service.list_work_items(pagination=pagination)

    assert len(result.work_items) == 2
    assert result.total_count == 5
    assert result.has_next is True
    assert result.offset == 0
    assert result.limit == 2

    # Get second page
    pagination = PaginationParams(offset=2, limit=2)
    result = await work_item_service.list_work_items(pagination=pagination)

    assert len(result.work_items) == 2
    assert result.has_next is True

    # Get third page
    pagination = PaginationParams(offset=4, limit=2)
    result = await work_item_service.list_work_items(pagination=pagination)

    assert len(result.work_items) == 1
    assert result.has_next is False


@pytest.mark.asyncio
async def test_list_work_items_with_project_filter(work_item_service: WorkItemService):
    """Test list with project ID filter."""
    # Create work items for different projects
    for project_id in ["project-1", "project-2"]:
        for i in range(2):
            command = CreateWorkItemCommand(
                title=f"Issue {i}",
                description="Description",
                project_id=project_id,
            )
            await work_item_service.create_work_item(command)

    filters = WorkItemFilters(project_id="project-1")
    result = await work_item_service.list_work_items(filters=filters)

    assert result.total_count == 2
    assert all(item.project_id == "project-1" for item in result.work_items)


@pytest.mark.asyncio
async def test_list_work_items_with_priority_filter(work_item_service: WorkItemService):
    """Test list with priority filter."""
    # Create work items with different priorities
    priorities = [WorkItemPriority.LOW, WorkItemPriority.MEDIUM, WorkItemPriority.HIGH]
    for priority in priorities:
        command = CreateWorkItemCommand(
            title="Issue",
            description="Description",
            project_id="project-123",
            priority=priority,
        )
        await work_item_service.create_work_item(command)

    filters = WorkItemFilters(priority=WorkItemPriority.HIGH)
    result = await work_item_service.list_work_items(filters=filters)

    assert result.total_count == 1
    assert result.work_items[0].priority == WorkItemPriority.HIGH


@pytest.mark.asyncio
async def test_list_work_items_with_label_filter(work_item_service: WorkItemService):
    """Test list with label filter."""
    # Create work items with different labels
    command1 = CreateWorkItemCommand(
        title="Issue 1",
        description="Description",
        project_id="project-123",
        labels=["bug", "critical"],
    )
    await work_item_service.create_work_item(command1)

    command2 = CreateWorkItemCommand(
        title="Issue 2",
        description="Description",
        project_id="project-123",
        labels=["feature"],
    )
    await work_item_service.create_work_item(command2)

    # Filter for items with "bug" label
    filters = WorkItemFilters(labels=["bug"])
    result = await work_item_service.list_work_items(filters=filters)

    assert result.total_count == 1
    assert "bug" in result.work_items[0].labels


@pytest.mark.asyncio
async def test_list_work_items_sorting_by_title(work_item_service: WorkItemService):
    """Test sorting work items by title."""
    titles = ["Charlie", "Alpha", "Bravo"]
    for title in titles:
        command = CreateWorkItemCommand(
            title=title,
            description="Description",
            project_id="project-123",
        )
        await work_item_service.create_work_item(command)

    pagination = PaginationParams(sort_by=SortField.TITLE, sort_order=SortOrder.ASC)
    result = await work_item_service.list_work_items(pagination=pagination)

    assert [item.title for item in result.work_items] == ["Alpha", "Bravo", "Charlie"]

    # Test descending
    pagination = PaginationParams(sort_by=SortField.TITLE, sort_order=SortOrder.DESC)
    result = await work_item_service.list_work_items(pagination=pagination)

    assert [item.title for item in result.work_items] == ["Charlie", "Bravo", "Alpha"]


@pytest.mark.asyncio
async def test_search_work_items(work_item_service: WorkItemService):
    """Test searching work items by title and description."""
    # Create work items
    command1 = CreateWorkItemCommand(
        title="Authentication Bug",
        description="Login is broken",
        project_id="project-123",
    )
    await work_item_service.create_work_item(command1)

    command2 = CreateWorkItemCommand(
        title="Database Performance",
        description="Queries are slow",
        project_id="project-123",
    )
    await work_item_service.create_work_item(command2)

    # Search for "login"
    search_params = WorkItemSearchParams(
        query="login",
        filters=WorkItemFilters(),
        pagination=PaginationParams(),
    )
    result = await work_item_service.search_work_items(search_params)

    assert result.total_count == 1
    assert "Authentication" in result.work_items[0].title


@pytest.mark.asyncio
async def test_count_work_items(work_item_service: WorkItemService):
    """Test counting work items."""
    # Create 3 work items
    for i in range(3):
        command = CreateWorkItemCommand(
            title=f"Issue {i}",
            description="Description",
            project_id="project-123",
        )
        await work_item_service.create_work_item(command)

    count = await work_item_service.count_work_items()

    assert count == 3


# Tests - Update Operations


@pytest.mark.asyncio
async def test_update_work_item_title_and_description(work_item_service: WorkItemService):
    """Test updating work item title and description."""
    # Create work item
    create_cmd = CreateWorkItemCommand(
        title="Original Title",
        description="Original Description",
        project_id="project-123",
    )
    created = await work_item_service.create_work_item(create_cmd)

    # Update work item
    update_cmd = UpdateWorkItemCommand(
        work_item_id=created.id,
        title="Updated Title",
        description="Updated Description",
    )
    updated = await work_item_service.update_work_item(update_cmd)

    # Verify the returned work item has updated values
    assert updated.title == "Updated Title"
    assert updated.description == "Updated Description"

    # Note: Title/description updates don't emit domain events in the current
    # implementation - they are updated directly. This means they persist in
    # the in-memory domain object but aren't stored in the event stream.
    # For a production system, we'd need to add proper domain methods that
    # emit events for title/description changes (see domain event catalog).


@pytest.mark.asyncio
async def test_update_work_item_labels(work_item_service: WorkItemService):
    """Test updating work item labels."""
    # Create work item with labels
    create_cmd = CreateWorkItemCommand(
        title="Issue",
        description="Description",
        project_id="project-123",
        labels=["bug"],
    )
    created = await work_item_service.create_work_item(create_cmd)

    # Update labels
    update_cmd = UpdateLabelsCommand(
        work_item_id=created.id,
        labels=["bug", "critical", "hotfix"],
    )
    updated = await work_item_service.update_labels(update_cmd)

    assert set(updated.labels) == {"bug", "critical", "hotfix"}


@pytest.mark.asyncio
async def test_update_work_item_priority(work_item_service: WorkItemService):
    """Test updating work item priority."""
    # Create work item
    create_cmd = CreateWorkItemCommand(
        title="Issue",
        description="Description",
        project_id="project-123",
        priority=WorkItemPriority.LOW,
    )
    created = await work_item_service.create_work_item(create_cmd)

    # Update priority
    update_cmd = UpdatePriorityCommand(
        work_item_id=created.id,
        priority=WorkItemPriority.CRITICAL,
    )
    updated = await work_item_service.update_priority(update_cmd)

    assert updated.priority == WorkItemPriority.CRITICAL


# Tests - Agent Assignment


@pytest.mark.asyncio
async def test_assign_agent(work_item_service: WorkItemService):
    """Test assigning agent to work item."""
    # Create work item
    create_cmd = CreateWorkItemCommand(
        title="Issue",
        description="Description",
        project_id="project-123",
    )
    created = await work_item_service.create_work_item(create_cmd)

    # Assign agent
    assign_cmd = AssignAgentCommand(
        work_item_id=created.id,
        agent_id="agent-123",
        reason="Agent has required skills",
    )
    updated = await work_item_service.assign_agent(assign_cmd)

    assert updated.assigned_agent_id == "agent-123"


# Tests - Workflow Operations


@pytest.mark.asyncio
async def test_attach_workflow(work_item_service: WorkItemService):
    """Test attaching workflow to work item."""
    # Create work item
    create_cmd = CreateWorkItemCommand(
        title="Issue",
        description="Description",
        project_id="project-123",
    )
    created = await work_item_service.create_work_item(create_cmd)

    # Attach workflow
    workflow_cmd = AttachWorkflowCommand(
        work_item_id=created.id,
        workflow_id="workflow-123",
    )
    updated = await work_item_service.attach_workflow(workflow_cmd)

    assert updated.current_workflow_id == "workflow-123"


@pytest.mark.asyncio
async def test_update_stage(work_item_service: WorkItemService):
    """Test updating work item stage."""
    # Create work item
    create_cmd = CreateWorkItemCommand(
        title="Issue",
        description="Description",
        project_id="project-123",
    )
    created = await work_item_service.create_work_item(create_cmd)

    # Attach workflow first
    workflow_cmd = AttachWorkflowCommand(
        work_item_id=created.id,
        workflow_id="workflow-123",
    )
    await work_item_service.attach_workflow(workflow_cmd)

    # Update stage
    stage_cmd = UpdateStageCommand(
        work_item_id=created.id,
        stage="review",
    )
    updated = await work_item_service.update_stage(stage_cmd)

    assert updated.current_stage == "review"


# Tests - History


@pytest.mark.asyncio
async def test_get_work_item_history(work_item_service: WorkItemService):
    """Test retrieving work item history."""
    # Create work item
    create_cmd = CreateWorkItemCommand(
        title="Issue",
        description="Description",
        project_id="project-123",
        labels=["bug"],
    )
    work_item = await work_item_service.create_work_item(create_cmd)

    # Make some updates
    update_cmd = UpdateLabelsCommand(
        work_item_id=work_item.id,
        labels=["bug", "critical"],
    )
    await work_item_service.update_labels(update_cmd)

    # Get history
    history = await work_item_service.get_work_item_history(work_item.id)

    assert history.work_item.id == work_item.id
    assert history.total_events >= 2  # At least create + update event
    assert len(history.events) == history.total_events


@pytest.mark.asyncio
async def test_get_work_item_history_with_limit(work_item_service: WorkItemService):
    """Test history with limit parameter."""
    # Create work item
    create_cmd = CreateWorkItemCommand(
        title="Issue",
        description="Description",
        project_id="project-123",
    )
    work_item = await work_item_service.create_work_item(create_cmd)

    # Get history with limit
    history = await work_item_service.get_work_item_history(work_item.id, limit=1)

    assert len(history.events) == 1


# Tests - Error Handling for Silent Failures


@pytest.mark.asyncio
async def test_list_work_items_with_corrupted_event_stream(
    work_item_service: WorkItemService,
    event_store: InMemoryEventStore,
    caplog: pytest.LogCaptureFixture,
):
    """Test that corrupted event streams are logged, not silently skipped."""
    # Create a valid work item first
    command = CreateWorkItemCommand(
        title="Valid Issue",
        description="Description",
        project_id="project-123",
    )
    await work_item_service.create_work_item(command)

    # Manually add a corrupted stream to the event store
    # This simulates event corruption
    corrupted_stream_id = "work-item-corrupted-123"

    # Create a mock event that will fail to reconstruct
    class BrokenEvent:
        def __init__(self):
            self.aggregate_id = "corrupted-123"
            self.occurred_at = datetime.now(UTC)

        @property
        def payload(self):
            raise RuntimeError("Simulated event reconstruction failure")

    # Add broken event to the store
    event_store._streams[corrupted_stream_id] = [BrokenEvent()]

    # Now list work items - should log the error but not crash
    with caplog.at_level(logging.ERROR):
        result = await work_item_service.list_work_items()

    # Verify we got the valid item
    assert result.total_count >= 1

    # Verify the error was logged
    assert any("Failed to reconstruct work item from event stream" in record.message for record in caplog.records)


@pytest.mark.asyncio
async def test_delete_work_item(work_item_service: WorkItemService):
    """Test soft deleting a work item."""
    # Create work item
    create_cmd = CreateWorkItemCommand(
        title="Issue",
        description="Description",
        project_id="project-123",
    )
    created = await work_item_service.create_work_item(create_cmd)

    # Delete work item
    result = await work_item_service.delete_work_item(created.id)

    assert result.success
    assert created.id in result.work_item_id


@pytest.mark.asyncio
async def test_date_filtering(work_item_service: WorkItemService):
    """Test filtering by date ranges."""
    # Create a work item
    command = CreateWorkItemCommand(
        title="Issue",
        description="Description",
        project_id="project-123",
    )
    work_item = await work_item_service.create_work_item(command)

    # Filter by created_after (before creation)
    filters = WorkItemFilters(created_after=datetime.now(UTC) - timedelta(hours=1))
    result = await work_item_service.list_work_items(filters=filters)

    assert result.total_count == 1

    # Filter by created_after (after creation)
    filters = WorkItemFilters(created_after=datetime.now(UTC) + timedelta(hours=1))
    result = await work_item_service.list_work_items(filters=filters)

    assert result.total_count == 0
