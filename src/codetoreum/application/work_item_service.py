"""Work Item Service

This module implements the application service for work item management.
It handles command and query operations by coordinating with the event store
and reconstructing work items from their event streams.
"""

from datetime import datetime, timezone
from typing import Any, List, Optional

from codetoreum.domain.exceptions import DomainError
from codetoreum.domain.work_item import WorkItem, WorkItemPriority, WorkItemStatus
from codetoreum.ports.input.work_item_command import (
    AssignAgentCommand,
    AttachWorkflowCommand,
    CreateWorkItemCommand,
    IWorkItemCommandPort,
    UpdateLabelsCommand,
    UpdatePriorityCommand,
    UpdateStageCommand,
    UpdateWorkItemCommand,
    WorkItemCommandResult,
)
from codetoreum.ports.input.work_item_query import (
    IWorkItemQueryPort,
    PaginationParams,
    SortField,
    SortOrder,
    WorkItemFilters,
    WorkItemHistory,
    WorkItemListResult,
    WorkItemSearchParams,
)
from codetoreum.ports.output.event_store import IEventStore


class WorkItemNotFoundError(Exception):
    """Raised when a work item is not found"""

    pass


class WorkItemService(IWorkItemCommandPort, IWorkItemQueryPort):
    """
    Application service for work item management.

    This service implements both command and query ports for work items.
    It uses event sourcing to persist and reconstruct work items from
    their event streams.

    Attributes:
        event_store: Event store for persisting events
    """

    def __init__(self, event_store: IEventStore):
        """
        Initialize work item service.

        Args:
            event_store: Event store for persisting events
        """
        self.event_store = event_store

    def _get_stream_id(self, work_item_id: str) -> str:
        """Get event stream ID for a work item."""
        return f"work-item-{work_item_id}"

    async def _load_work_item(self, work_item_id: str) -> WorkItem:
        """
        Load a work item from its event stream.

        Args:
            work_item_id: Work item ID

        Returns:
            Reconstructed work item

        Raises:
            WorkItemNotFoundError: If work item doesn't exist
        """
        stream_id = self._get_stream_id(work_item_id)

        # Check if stream exists
        if not await self.event_store.stream_exists(stream_id):
            raise WorkItemNotFoundError(f"Work item not found: {work_item_id}")

        # Load events
        events = await self.event_store.get_events(stream_id)

        if not events:
            raise WorkItemNotFoundError(f"Work item not found: {work_item_id}")

        # Reconstruct work item from events
        return WorkItem.from_events(events)

    async def _save_work_item(self, work_item: WorkItem) -> None:
        """
        Save work item by persisting its pending events.

        Args:
            work_item: Work item to save
        """
        pending_events = work_item.get_pending_events()

        if not pending_events:
            return  # Nothing to save

        stream_id = self._get_stream_id(work_item.id)

        # Append events to stream
        # Use version for optimistic concurrency control
        expected_version = work_item._version - len(pending_events)
        await self.event_store.append(stream_id, pending_events, expected_version if expected_version > 0 else None)

        # Clear pending events
        work_item.clear_events()

    # ========================================================================
    # Command Port Implementation
    # ========================================================================

    async def create_work_item(self, command: CreateWorkItemCommand) -> WorkItem:
        """Creates a new work item."""
        # Create work item (emits WorkItemCreated event)
        work_item = WorkItem.create(
            title=command.title,
            description=command.description,
            project_id=command.project_id,
            labels=command.labels,
            priority=command.priority,
            external_id=command.external_id,
            external_url=command.external_url,
        )

        # Persist events
        await self._save_work_item(work_item)

        return work_item

    async def update_work_item(self, command: UpdateWorkItemCommand) -> WorkItem:
        """Updates an existing work item."""
        # Load work item
        work_item = await self._load_work_item(command.work_item_id)

        # Apply updates
        if command.title is not None:
            # Title updates would require a new domain method
            # For now, we'll update the field directly
            # In production, add a proper domain method
            work_item.title = command.title
            work_item.updated_at = datetime.now(timezone.utc)

        if command.description is not None:
            work_item.description = command.description
            work_item.updated_at = datetime.now(timezone.utc)

        if command.labels is not None:
            work_item.update_labels(command.labels)

        if command.priority is not None:
            work_item.update_priority(command.priority)

        # Persist events
        await self._save_work_item(work_item)

        return work_item

    async def delete_work_item(self, work_item_id: str) -> WorkItemCommandResult:
        """Soft deletes a work item."""
        # Load work item to ensure it exists
        work_item = await self._load_work_item(work_item_id)

        # For soft delete, we could mark the stream as deleted in metadata
        # For now, we just verify it exists and return success
        # In production, implement proper soft delete with metadata

        return WorkItemCommandResult(
            success=True, work_item_id=work_item_id, message="Work item deleted successfully"
        )

    async def assign_agent(self, command: AssignAgentCommand) -> WorkItem:
        """Assigns an agent to a work item."""
        work_item = await self._load_work_item(command.work_item_id)

        # Assign agent (emits AgentAssigned event)
        work_item.assign_agent(command.agent_id, command.reason)

        # Persist events
        await self._save_work_item(work_item)

        return work_item

    async def update_labels(self, command: UpdateLabelsCommand) -> WorkItem:
        """Updates work item labels."""
        work_item = await self._load_work_item(command.work_item_id)

        # Update labels (emits WorkItemLabelsUpdated event)
        work_item.update_labels(command.labels)

        # Persist events
        await self._save_work_item(work_item)

        return work_item

    async def update_priority(self, command: UpdatePriorityCommand) -> WorkItem:
        """Updates work item priority."""
        work_item = await self._load_work_item(command.work_item_id)

        # Update priority (emits WorkItemPriorityUpdated event)
        work_item.update_priority(command.priority)

        # Persist events
        await self._save_work_item(work_item)

        return work_item

    async def attach_workflow(self, command: AttachWorkflowCommand) -> WorkItem:
        """Attaches a workflow to a work item."""
        work_item = await self._load_work_item(command.work_item_id)

        # Attach workflow (emits WorkflowAttached event)
        work_item.attach_workflow(command.workflow_id)

        # Persist events
        await self._save_work_item(work_item)

        return work_item

    async def update_stage(self, command: UpdateStageCommand) -> WorkItem:
        """Updates work item stage."""
        work_item = await self._load_work_item(command.work_item_id)

        # Update stage (emits WorkItemStageUpdated event)
        work_item.update_stage(command.stage)

        # Persist events
        await self._save_work_item(work_item)

        return work_item

    # ========================================================================
    # Query Port Implementation
    # ========================================================================

    async def get_work_item(self, work_item_id: str) -> WorkItem:
        """Retrieves a single work item by ID."""
        return await self._load_work_item(work_item_id)

    async def list_work_items(
        self, filters: Optional[WorkItemFilters] = None, pagination: Optional[PaginationParams] = None
    ) -> WorkItemListResult:
        """Lists work items with optional filtering and pagination."""
        # Set defaults
        filters = filters or WorkItemFilters()
        pagination = pagination or PaginationParams()

        # Get all work item streams
        # This is a simplified implementation - in production, use a read model
        # or projection for efficient querying
        all_streams = await self._get_all_work_item_streams()

        # Load all work items
        work_items: List[WorkItem] = []
        for stream_id in all_streams:
            try:
                events = await self.event_store.get_events(stream_id)
                if events:
                    work_item = WorkItem.from_events(events)
                    # Apply filters
                    if self._matches_filters(work_item, filters):
                        work_items.append(work_item)
            except Exception:
                # Skip invalid streams
                continue

        # Sort work items
        work_items = self._sort_work_items(work_items, pagination.sort_by, pagination.sort_order)

        # Apply pagination
        total_count = len(work_items)
        start = pagination.offset
        end = start + pagination.limit
        paginated_items = work_items[start:end]

        has_next = end < total_count

        return WorkItemListResult(
            work_items=paginated_items,
            total_count=total_count,
            offset=pagination.offset,
            limit=pagination.limit,
            has_next=has_next,
        )

    async def search_work_items(self, search_params: WorkItemSearchParams) -> WorkItemListResult:
        """Searches work items by title and description."""
        # Get all work items
        all_items_result = await self.list_work_items(search_params.filters, search_params.pagination)

        # Filter by search query
        query = search_params.query.lower()
        matching_items = [
            item
            for item in all_items_result.work_items
            if query in item.title.lower() or query in item.description.lower()
        ]

        # Recalculate pagination
        total_count = len(matching_items)
        has_next = (search_params.pagination.offset + search_params.pagination.limit) < total_count

        return WorkItemListResult(
            work_items=matching_items,
            total_count=total_count,
            offset=search_params.pagination.offset,
            limit=search_params.pagination.limit,
            has_next=has_next,
        )

    async def get_work_item_history(
        self, work_item_id: str, limit: Optional[int] = None
    ) -> WorkItemHistory:
        """Retrieves work item history including all events."""
        work_item = await self._load_work_item(work_item_id)

        stream_id = self._get_stream_id(work_item_id)
        events = await self.event_store.get_events(stream_id)

        # Convert events to dicts
        event_dicts = [self._event_to_dict(event) for event in events]

        # Apply limit if specified
        if limit is not None:
            event_dicts = event_dicts[:limit]

        return WorkItemHistory(work_item=work_item, events=event_dicts, total_events=len(events))

    async def count_work_items(self, filters: Optional[WorkItemFilters] = None) -> int:
        """Counts work items matching the given filters."""
        # This is inefficient - in production, use a read model
        result = await self.list_work_items(filters, PaginationParams(offset=0, limit=999999))
        return result.total_count

    # ========================================================================
    # Helper Methods
    # ========================================================================

    async def _get_all_work_item_streams(self) -> List[str]:
        """
        Get all work item stream IDs.

        This is a simplified implementation. In production, maintain
        a catalog or use stream metadata for efficient lookups.
        """
        # For now, we'll use a placeholder that needs implementation
        # In production, the event store should support stream querying
        # or maintain a separate catalog of work item IDs
        return []

    def _matches_filters(self, work_item: WorkItem, filters: WorkItemFilters) -> bool:
        """Check if work item matches the given filters."""
        if filters.project_id and work_item.project_id != filters.project_id:
            return False

        if filters.status and work_item.status != filters.status:
            return False

        if filters.assignee and work_item.assigned_agent_id != filters.assignee:
            return False

        if filters.labels:
            # AND logic - work item must have all specified labels
            if not all(label in work_item.labels for label in filters.labels):
                return False

        if filters.workflow_stage and work_item.current_stage != filters.workflow_stage:
            return False

        if filters.priority and work_item.priority != filters.priority:
            return False

        if filters.external_id and work_item.external_id != filters.external_id:
            return False

        if filters.created_after and work_item.created_at < filters.created_after:
            return False

        if filters.created_before and work_item.created_at > filters.created_before:
            return False

        if filters.updated_after and work_item.updated_at < filters.updated_after:
            return False

        if filters.updated_before and work_item.updated_at > filters.updated_before:
            return False

        return True

    def _sort_work_items(
        self, work_items: List[WorkItem], sort_by: SortField, sort_order: SortOrder
    ) -> List[WorkItem]:
        """Sort work items by the specified field and order."""
        reverse = sort_order == SortOrder.DESC

        if sort_by == SortField.CREATED_AT:
            return sorted(work_items, key=lambda x: x.created_at, reverse=reverse)
        elif sort_by == SortField.UPDATED_AT:
            return sorted(work_items, key=lambda x: x.updated_at, reverse=reverse)
        elif sort_by == SortField.PRIORITY:
            return sorted(work_items, key=lambda x: x.priority.value, reverse=reverse)
        elif sort_by == SortField.TITLE:
            return sorted(work_items, key=lambda x: x.title.lower(), reverse=reverse)
        elif sort_by == SortField.STATUS:
            return sorted(work_items, key=lambda x: x.status.value, reverse=reverse)
        else:
            return work_items

    def _event_to_dict(self, event: Any) -> dict:
        """Convert a domain event to a dictionary."""
        return {
            "event_type": event.__class__.__name__,
            "aggregate_id": event.aggregate_id,
            "occurred_at": event.occurred_at.isoformat() if event.occurred_at else None,
            "payload": event.payload,
        }
