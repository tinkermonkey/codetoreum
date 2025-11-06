"""Work Item Query Input Port

This module defines the input port interface for work item query operations,
including listing, filtering, and searching work items.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import List, Optional

from codetoreum.domain.work_item import WorkItem, WorkItemPriority, WorkItemStatus


class SortOrder(Enum):
    """Sort order for query results"""

    ASC = "asc"
    DESC = "desc"


class SortField(Enum):
    """Fields that can be used for sorting"""

    CREATED_AT = "created_at"
    UPDATED_AT = "updated_at"
    PRIORITY = "priority"
    TITLE = "title"
    STATUS = "status"


@dataclass
class WorkItemFilters:
    """Filters for querying work items"""

    project_id: Optional[str] = None
    status: Optional[WorkItemStatus] = None
    assignee: Optional[str] = None  # Agent ID
    labels: Optional[List[str]] = None  # AND logic for multiple labels
    workflow_stage: Optional[str] = None
    priority: Optional[WorkItemPriority] = None
    external_id: Optional[str] = None
    created_after: Optional[datetime] = None
    created_before: Optional[datetime] = None
    updated_after: Optional[datetime] = None
    updated_before: Optional[datetime] = None


@dataclass
class PaginationParams:
    """Pagination parameters"""

    offset: int = 0
    limit: int = 20
    sort_by: SortField = SortField.UPDATED_AT
    sort_order: SortOrder = SortOrder.DESC


@dataclass
class WorkItemSearchParams:
    """Search parameters for work items"""

    query: str  # Search in title and description
    filters: Optional[WorkItemFilters] = None
    pagination: PaginationParams = field(default_factory=PaginationParams)


@dataclass
class WorkItemListResult:
    """Result of listing work items"""

    work_items: List[WorkItem]
    total_count: int
    offset: int
    limit: int
    has_next: bool


@dataclass
class WorkItemHistory:
    """History of a work item including all events"""

    work_item: WorkItem
    events: List[dict]  # Domain events as dicts
    total_events: int


class IWorkItemQueryPort(ABC):
    """
    Input port for work item queries.

    This port handles read-only operations for work items,
    including listing, filtering, searching, and retrieving details.
    """

    @abstractmethod
    async def get_work_item(self, work_item_id: str) -> WorkItem:
        """
        Retrieves a single work item by ID.

        Args:
            work_item_id: Work item ID

        Returns:
            Work item

        Raises:
            WorkItemNotFoundError: If work item doesn't exist
        """
        pass

    @abstractmethod
    async def list_work_items(
        self, filters: Optional[WorkItemFilters] = None, pagination: Optional[PaginationParams] = None
    ) -> WorkItemListResult:
        """
        Lists work items with optional filtering and pagination.

        Args:
            filters: Optional filters to apply
            pagination: Optional pagination parameters

        Returns:
            List result with work items and metadata
        """
        pass

    @abstractmethod
    async def search_work_items(self, search_params: WorkItemSearchParams) -> WorkItemListResult:
        """
        Searches work items by title and description.

        Args:
            search_params: Search parameters including query and filters

        Returns:
            List result with matching work items
        """
        pass

    @abstractmethod
    async def get_work_item_history(
        self, work_item_id: str, limit: Optional[int] = None
    ) -> WorkItemHistory:
        """
        Retrieves work item history including all events.

        Args:
            work_item_id: Work item ID
            limit: Optional limit on number of events

        Returns:
            Work item history with events

        Raises:
            WorkItemNotFoundError: If work item doesn't exist
        """
        pass

    @abstractmethod
    async def count_work_items(self, filters: Optional[WorkItemFilters] = None) -> int:
        """
        Counts work items matching the given filters.

        Args:
            filters: Optional filters to apply

        Returns:
            Count of matching work items
        """
        pass
