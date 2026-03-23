"""Mock work item service adapter for testing and simulation.

This adapter provides a deterministic, in-memory implementation of IWorkItemService
for use in unit tests, integration tests, and simulation mode.
"""

import logging
import threading
from collections.abc import Callable
from datetime import UTC, datetime

from codetoreum.adapters.secondary.mock_event_emitter import MockEventEmitter
from codetoreum.domain.events.work_item_events import (
    WorkItemCreatedEvent,
    WorkItemUpdatedEvent,
)
from codetoreum.domain.types import ProjectId, WorkItemId
from codetoreum.domain.work_item import WorkItem, WorkItemPriority
from codetoreum.ports.exceptions import (
    ResourceNotFoundError,
    ValidationError,
)
from codetoreum.ports.output.monitoring import (
    MonitoringConfig,
    MonitoringState,
    MonitoringStatus,
)
from codetoreum.ports.output.work_item_service import IWorkItemService

logger = logging.getLogger(__name__)


class MockWorkItemService(MockEventEmitter, IWorkItemService):
    """Mock implementation of IWorkItemService for testing and simulation.

    This adapter provides:
    - In-memory work item storage
    - Event emission for creation and updates
    - Monitoring lifecycle control (start/stop)
    - Thread-safe concurrent operations

    Attributes:
        work_items: Dictionary mapping work item IDs to WorkItem instances
        monitoring_status: Dictionary mapping project IDs to MonitoringStatus
        event_listeners: Dictionary mapping event types to handler lists

    Example:
        # Setup
        adapter = MockWorkItemService()

        # Subscribe to events
        created_events = []
        adapter.on("workitem.created", created_events.append)

        # Create work item
        item = await adapter.create_work_item(
            project_id="proj-1",
            title="New feature",
            description="Implementation details"
        )

        # Verify event was emitted
        assert len(created_events) == 1
        assert created_events[0].work_item_id == item.id
    """

    def __init__(self, time_source: Callable[[], datetime] | None = None) -> None:
        """Initialize the mock work item service.

        Args:
            time_source: Optional callable returning current datetime for simulation clock control.
                        Defaults to datetime.now(UTC).
        """
        super().__init__()
        self._work_items: dict[str, WorkItem] = {}
        self._monitoring_status: dict[str, MonitoringStatus] = {}
        self._lock = threading.Lock()
        self._time_source = time_source or (lambda: datetime.now(UTC))

    # ===== Monitoring Lifecycle =====

    async def start_monitoring(self, project_id: str, config: MonitoringConfig) -> None:
        """Start monitoring for work item changes.

        Args:
            project_id: Project to monitor
            config: Monitoring configuration

        Raises:
            ValidationError: If project_id is invalid
        """
        if not project_id or not project_id.strip():
            msg = "project_id cannot be empty"
            raise ValidationError(msg)

        with self._lock:
            status = MonitoringStatus(
                state=MonitoringState.ACTIVE,
                project_id=project_id,
                started_at=self._time_source().isoformat(),
            )
            self._monitoring_status[project_id] = status
            logger.debug(f"Started monitoring work items for project {project_id}")

    async def stop_monitoring(self, project_id: str) -> None:
        """Stop monitoring for work item changes.

        Args:
            project_id: Project to stop monitoring

        Raises:
            ValidationError: If project_id is invalid
        """
        if not project_id or not project_id.strip():
            msg = "project_id cannot be empty"
            raise ValidationError(msg)

        with self._lock:
            if project_id in self._monitoring_status:
                status = self._monitoring_status[project_id]
                status = MonitoringStatus(
                    state=MonitoringState.STOPPED,
                    project_id=project_id,
                    started_at=status.started_at,
                )
                self._monitoring_status[project_id] = status
                logger.debug(f"Stopped monitoring work items for project {project_id}")

    async def get_monitoring_status(self, project_id: str) -> MonitoringStatus:
        """Get monitoring status for a project.

        Args:
            project_id: Project to query

        Returns:
            Current monitoring status

        Raises:
            ValidationError: If project_id is invalid
        """
        if not project_id or not project_id.strip():
            msg = "project_id cannot be empty"
            raise ValidationError(msg)

        with self._lock:
            if project_id not in self._monitoring_status:
                return MonitoringStatus(
                    state=MonitoringState.STOPPED,
                    project_id=project_id,
                )
            return self._monitoring_status[project_id]

    # ===== Query Operations =====

    async def get_work_item(self, item_id: WorkItemId) -> WorkItem:
        """Retrieve a work item by ID.

        Args:
            item_id: Work item identifier

        Returns:
            The requested work item

        Raises:
            ResourceNotFoundError: If work item doesn't exist
        """
        with self._lock:
            work_item = self._work_items.get(str(item_id))
            if not work_item:
                msg = "WorkItem"
                raise ResourceNotFoundError(msg, str(item_id))
            return work_item

    async def get_work_items_by_status(self, project_id: ProjectId, status: str) -> list[WorkItem]:
        """Query work items by status.

        Args:
            project_id: Project to query
            status: Status filter

        Returns:
            List of work items matching the status
        """
        with self._lock:
            return [
                wi for wi in self._work_items.values() if wi.project_id == str(project_id) and wi.status.value == status
            ]

    async def get_work_items_by_column(self, project_id: ProjectId, column_name: str) -> list[WorkItem]:
        """Query work items in a specific board column.

        Args:
            project_id: Project to query
            column_name: Column name

        Returns:
            List of work items in the column
        """
        # For now, return empty list as board integration is separate concern
        return []

    # ===== Command Operations =====

    async def create_work_item(self, project_id: ProjectId, title: str, description: str, **kwargs) -> WorkItem:
        """Create a new work item and emit creation event.

        Args:
            project_id: Project to create work item in
            title: Work item title
            description: Work item description
            **kwargs: Additional fields (labels, priority, etc.)

        Returns:
            The created work item

        Raises:
            ValidationError: If required fields are invalid

        Events:
            Emits 'workitem.created' event
        """
        if not title or not title.strip():
            msg = "title cannot be empty"
            raise ValidationError(msg)

        if not project_id:
            msg = "project_id cannot be empty"
            raise ValidationError(msg)

        with self._lock:
            # Create the work item
            work_item = WorkItem.create(
                title=title,
                description=description or "",
                project_id=str(project_id),
                labels=kwargs.get("labels", []),
                priority=kwargs.get("priority", WorkItemPriority.MEDIUM),
                external_id=f"work-item-{len(self._work_items) + 1}",
                external_url="",
            )

            self._work_items[work_item.id] = work_item

            # Emit creation event
            event = WorkItemCreatedEvent(
                type="workitem.created",
                timestamp=self._time_source().isoformat(),
                source="mock",
                work_item_id=work_item.id,
                project_id=str(project_id),
                title=title,
            )

            # Clear events from the domain model and emit the domain event
            work_item.clear_events()
            self.emit(event)

            return work_item

    async def update_work_item(self, item_id: WorkItemId, updates: dict) -> WorkItem:
        """Update a work item and emit update event.

        Args:
            item_id: Work item to update
            updates: Dictionary of fields to update

        Returns:
            The updated work item

        Raises:
            ResourceNotFoundError: If work item doesn't exist
            ValidationError: If updates are invalid

        Events:
            Emits 'workitem.updated' event
        """
        if not item_id:
            msg = "item_id cannot be empty"
            raise ValidationError(msg)

        if not updates:
            msg = "updates cannot be empty"
            raise ValidationError(msg)

        work_item = await self.get_work_item(item_id)

        with self._lock:
            # Apply updates
            if "title" in updates:
                work_item.title = updates["title"]
            if "description" in updates:
                work_item.description = updates["description"]
            if "labels" in updates:
                work_item.update_labels(updates["labels"])
            if "priority" in updates:
                priority = updates["priority"]
                if isinstance(priority, str):
                    priority = WorkItemPriority[priority.upper()]
                work_item.update_priority(priority)

            work_item.updated_at = self._time_source()

            # Emit update event
            event = WorkItemUpdatedEvent(
                type="workitem.updated",
                timestamp=self._time_source().isoformat(),
                source="mock",
                work_item_id=work_item.id,
                project_id=work_item.project_id,
                changes=dict(updates),
            )

            work_item.clear_events()
            self.emit(event)

            return work_item

    # ===== Testing Helpers =====

    def add_work_item(self, work_item: WorkItem) -> None:
        """Insert a work item directly into storage (for test/simulation seeding).

        Args:
            work_item: Work item to add
        """
        with self._lock:
            self._work_items[work_item.id] = work_item

    def clear(self) -> None:
        """Clear all stored data for testing."""
        with self._lock:
            self._work_items.clear()
            self._monitoring_status.clear()
            self._handlers.clear()

    def reset_monitoring(self) -> None:
        """Reset monitoring status for all projects."""
        with self._lock:
            self._monitoring_status.clear()

    def get_all_work_items(self) -> list[WorkItem]:
        """Get all work items (for testing).

        Returns:
            List of all work items in storage
        """
        with self._lock:
            return list(self._work_items.values())
