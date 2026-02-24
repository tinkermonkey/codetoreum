"""
Mock Work Item Query Adapter

In-memory implementation of IWorkItemQueryPort for development and testing.

Supports optional backing store injection: when an InMemoryTicketAdapter is provided,
reads delegate to it. When no backing store is provided (unit tests), the adapter
uses its own internal dictionaries.
"""

from threading import RLock
from typing import TYPE_CHECKING, Optional

from codetoreum.domain.exceptions import WorkItemNotFoundError
from codetoreum.domain.work_item import WorkItem
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

if TYPE_CHECKING:
    from codetoreum.adapters.testing.in_memory_ticket_adapter import (
        InMemoryTicketAdapter,
    )


class MockWorkItemQueryAdapter(IWorkItemQueryPort):
    """
    Mock implementation of IWorkItemQueryPort using in-memory storage.

    When ``ticket_adapter`` is provided, query methods delegate to it for
    work item storage. This eliminates dual-writes in simulation seeding.
    """

    def __init__(self, ticket_adapter: Optional["InMemoryTicketAdapter"] = None):
        self._ticket_adapter = ticket_adapter
        self._work_items: dict[str, WorkItem] = {}
        self._events: dict[str, list[dict]] = {}  # work_item_id -> events
        self._lock = RLock()

    def add_work_item(self, work_item: WorkItem):
        """Helper method to add a work item to mock storage."""
        with self._lock:
            self._work_items[work_item.id] = work_item
            if work_item.id not in self._events:
                self._events[work_item.id] = []

    def add_event(self, work_item_id: str, event: dict):
        """Helper method to add an event for a work item."""
        with self._lock:
            if work_item_id not in self._events:
                self._events[work_item_id] = []
            self._events[work_item_id].append(event)

    @property
    def _all_work_items(self) -> dict[str, WorkItem]:
        """Return the work items dict, preferring the backing store if available."""
        if self._ticket_adapter:
            return self._ticket_adapter._work_items
        return self._work_items

    async def get_work_item(self, work_item_id: str) -> WorkItem:
        """Retrieves a single work item by ID."""
        if self._ticket_adapter:
            return await self._ticket_adapter.get_work_item(work_item_id)
        with self._lock:
            if work_item_id not in self._work_items:
                raise WorkItemNotFoundError(f"Work item with ID {work_item_id} not found")
            return self._work_items[work_item_id]

    async def list_work_items(
        self,
        filters: WorkItemFilters | None = None,
        pagination: PaginationParams | None = None,
    ) -> WorkItemListResult:
        """Lists work items with optional filtering and pagination."""
        with self._lock:
            # Get all work items
            work_items = list(self._all_work_items.values())

            # Apply filters
            if filters:
                work_items = self._apply_filters(work_items, filters)

            # Sort work items
            if pagination:
                work_items = self._sort_work_items(work_items, pagination)

            total_count = len(work_items)

            # Apply pagination
            offset = 0
            limit = 20
            if pagination:
                offset = pagination.offset
                limit = pagination.limit

            paginated_items = work_items[offset : offset + limit]
            has_next = (offset + limit) < total_count

            return WorkItemListResult(
                work_items=paginated_items,
                total_count=total_count,
                offset=offset,
                limit=limit,
                has_next=has_next,
            )

    async def search_work_items(
        self, search_params: WorkItemSearchParams
    ) -> WorkItemListResult:
        """Searches work items by title and description."""
        with self._lock:
            # Get all work items
            work_items = list(self._all_work_items.values())

            # Apply search query (simple case-insensitive substring match)
            query_lower = search_params.query.lower()
            work_items = [
                wi
                for wi in work_items
                if query_lower in wi.title.lower() or query_lower in wi.description.lower()
            ]

            # Apply filters if provided
            if search_params.filters:
                work_items = self._apply_filters(work_items, search_params.filters)

            # Sort work items
            work_items = self._sort_work_items(work_items, search_params.pagination)

            total_count = len(work_items)

            # Apply pagination
            offset = search_params.pagination.offset
            limit = search_params.pagination.limit

            paginated_items = work_items[offset : offset + limit]
            has_next = (offset + limit) < total_count

            return WorkItemListResult(
                work_items=paginated_items,
                total_count=total_count,
                offset=offset,
                limit=limit,
                has_next=has_next,
            )

    async def get_work_item_history(
        self, work_item_id: str, limit: int | None = None
    ) -> WorkItemHistory:
        """Retrieves work item history including all events."""
        with self._lock:
            items = self._all_work_items
            if work_item_id not in items:
                raise WorkItemNotFoundError(f"Work item with ID {work_item_id} not found")

            work_item = items[work_item_id]
            events = self._events.get(work_item_id, [])

            # Apply limit if specified
            if limit:
                events = events[-limit:]

            return WorkItemHistory(
                work_item=work_item,
                events=events,
                total_events=len(self._events.get(work_item_id, [])),
            )

    async def count_work_items(self, filters: WorkItemFilters | None = None) -> int:
        """Counts work items matching the given filters."""
        with self._lock:
            work_items = list(self._all_work_items.values())

            if filters:
                work_items = self._apply_filters(work_items, filters)

            return len(work_items)

    def _apply_filters(
        self, work_items: list[WorkItem], filters: WorkItemFilters
    ) -> list[WorkItem]:
        """Apply filters to work item list."""
        result = work_items

        if filters.project_id is not None:
            result = [wi for wi in result if wi.project_id == filters.project_id]

        if filters.status is not None:
            result = [wi for wi in result if wi.status == filters.status]

        if filters.assignee is not None:
            result = [wi for wi in result if wi.assignee == filters.assignee]

        if filters.labels is not None:
            # AND logic for multiple labels
            for label in filters.labels:
                result = [wi for wi in result if label in wi.labels]

        if filters.workflow_stage is not None:
            result = [wi for wi in result if wi.workflow_stage == filters.workflow_stage]

        if filters.priority is not None:
            result = [wi for wi in result if wi.priority == filters.priority]

        if filters.external_id is not None:
            result = [wi for wi in result if wi.external_id == filters.external_id]

        if filters.created_after is not None:
            result = [wi for wi in result if wi.created_at >= filters.created_after]

        if filters.created_before is not None:
            result = [wi for wi in result if wi.created_at <= filters.created_before]

        if filters.updated_after is not None:
            result = [wi for wi in result if wi.updated_at >= filters.updated_after]

        if filters.updated_before is not None:
            result = [wi for wi in result if wi.updated_at <= filters.updated_before]

        return result

    def _sort_work_items(
        self, work_items: list[WorkItem], pagination: PaginationParams
    ) -> list[WorkItem]:
        """Sort work items based on pagination parameters."""
        reverse = pagination.sort_order == SortOrder.DESC

        if pagination.sort_by == SortField.CREATED_AT:
            work_items.sort(key=lambda wi: wi.created_at, reverse=reverse)
        elif pagination.sort_by == SortField.UPDATED_AT:
            work_items.sort(key=lambda wi: wi.updated_at, reverse=reverse)
        elif pagination.sort_by == SortField.PRIORITY:
            # Priority order: CRITICAL > HIGH > MEDIUM > LOW
            priority_order = {"CRITICAL": 4, "HIGH": 3, "MEDIUM": 2, "LOW": 1}
            work_items.sort(
                key=lambda wi: priority_order.get(wi.priority.value, 0),
                reverse=reverse,
            )
        elif pagination.sort_by == SortField.TITLE:
            work_items.sort(key=lambda wi: wi.title, reverse=reverse)
        elif pagination.sort_by == SortField.STATUS:
            work_items.sort(key=lambda wi: wi.status.value, reverse=reverse)

        return work_items

    def clear(self):
        """Clear all data (useful for testing)."""
        with self._lock:
            self._work_items.clear()
            self._events.clear()
