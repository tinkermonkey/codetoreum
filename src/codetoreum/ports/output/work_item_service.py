"""Work item service port interface with event emission.

This interface extends ITicketSystem with event emission capabilities
and monitoring lifecycle, enabling the orchestrator to:
1. Query work items and their status
2. React to work item changes via events
3. Control when change detection is active

Work items are units of work (issues, tasks, features) that flow through
the orchestrator. They carry metadata about status, assignment, and progress.
"""

from abc import ABC, abstractmethod
from typing import Any

from codetoreum.domain.types import ProjectId, WorkItemId
from codetoreum.domain.work_item import WorkItem

from .event_emitter import IEventEmitter
from .monitoring import IMonitoredService


class IWorkItemService(IEventEmitter, IMonitoredService, ABC):
    """Work item management with event emission.

    Combines ITicketSystem operations with event emission for work item
    changes and monitoring lifecycle control. Services implement this
    interface to provide vendor-agnostic work item management.

    Events emitted:
        - 'workitem.created' → WorkItemCreatedEvent
        - 'workitem.updated' → WorkItemUpdatedEvent
        - 'workitem.status_changed' → Status change detection

    Example: async with service as svc:
            # Start monitoring for changes
            await svc.start_monitoring(
                project_id="proj-123",
                config=MonitoringConfig(project_id="proj-123")
            )

            # Subscribe to events
            svc.on("workitem.created", handle_creation)

            # Query work items
            item = await svc.get_work_item("issue-456")

            # Stop when done
            await svc.stop_monitoring("proj-123")
    """

    # Query Operations

    @abstractmethod
    async def get_work_item(self, item_id: WorkItemId) -> WorkItem:
        """Retrieve a work item by ID.

        Args: item_id: Unique identifier for the work item

        Returns: WorkItem: The requested work item with all details

        Raises: WorkItemNotFoundError: Work item doesn't exist
            ValidationError: Invalid item_id format
            ExternalServiceError: Service communication failure
        """

    @abstractmethod
    async def get_work_items_by_status(self, project_id: ProjectId, status: str) -> list[WorkItem]:
        """Query work items by status.

        Returns all work items in a given project with the specified status.

        Args: project_id: Project to query
            status: Status filter (e.g., "open", "closed", "in_progress")

        Returns: List[WorkItem]: Work items matching the status filter

        Raises: ProjectNotFoundError: Project doesn't exist
            ValidationError: Invalid status value
            ExternalServiceError: Service communication failure
        """

    @abstractmethod
    async def get_work_items_by_column(self, project_id: ProjectId, column_name: str) -> list[WorkItem]:
        """Query work items in a specific board column.

        Returns all work items currently assigned to a column on a project board.

        Args: project_id: Project containing the board
            column_name: Column name (e.g., "Backlog", "In Progress", "Done")

        Returns: List[WorkItem]: Work items in the column

        Raises: ProjectNotFoundError: Project doesn't exist
            ValidationError: Invalid column_name
            ExternalServiceError: Service communication failure
        """

    # Command Operations

    @abstractmethod
    async def update_work_item(self, item_id: WorkItemId, updates: dict[str, Any]) -> WorkItem:
        """Update a work item and emit update event.

        Updates specified fields and emits 'workitem.updated' event.
        Supported update fields depend on the ticket system implementation
        but typically include: title, description, status, assignee, labels.

        Args: item_id: Work item to update
            updates: Dictionary of fields to update
                    e.g., {"status": "in_progress", "assignee": "user-123"}

        Returns: WorkItem: Updated work item state

        Raises: WorkItemNotFoundError: Work item doesn't exist
            ValidationError: Invalid update data or field names
            ExternalServiceError: Service communication failure

        Events: Emits 'workitem.updated' event with updated state
        """

    @abstractmethod
    async def create_work_item(self, project_id: ProjectId, title: str, description: str, **kwargs: Any) -> WorkItem:
        """Create a new work item and emit creation event.

        Args: project_id: Project to create item in
            title: Work item title
            description: Work item description
            **kwargs: Additional fields (labels, assignee, etc.)

        Returns: WorkItem: Newly created work item

        Raises: ProjectNotFoundError: Project doesn't exist
            ValidationError: Invalid input data
            ExternalServiceError: Service communication failure

        Events: Emits 'workitem.created' event with new work item
        """

    @abstractmethod
    async def get_child_issues(self, parent_id: WorkItemId) -> list[WorkItem]:
        """Retrieve all child work items created under a parent.

        Args: parent_id: ID of the parent work item

        Returns: list[WorkItem]: Child work items in creation order (empty if none)

        Raises: WorkItemNotFoundError: Parent work item doesn't exist
        """
