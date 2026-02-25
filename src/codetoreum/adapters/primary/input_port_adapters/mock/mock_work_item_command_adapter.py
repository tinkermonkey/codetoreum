"""
Mock Work Item Command Adapter

In-memory implementation of IWorkItemCommandPort for development and testing.
"""

from datetime import UTC, datetime
from threading import RLock
from uuid import uuid4

from codetoreum.domain.exceptions import WorkItemNotFoundError
from codetoreum.domain.work_item import WorkItem, WorkItemStatus
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


class MockWorkItemCommandAdapter(IWorkItemCommandPort):
    """
    Mock implementation of IWorkItemCommandPort using in-memory storage.
    """

    def __init__(self):
        self._work_items: dict[str, WorkItem] = {}
        self._lock = RLock()

    async def create_work_item(self, command: CreateWorkItemCommand) -> WorkItem:
        """Creates a new work item."""
        with self._lock:
            now = datetime.now(UTC)

            work_item = WorkItem(
                id=str(uuid4()),
                project_id=command.project_id,
                title=command.title,
                description=command.description,
                status=WorkItemStatus.NEW,
                priority=command.priority,
                assigned_agent_id=None,
                assigned_at=None,
                labels=command.labels or [],
                current_workflow_id=None,
                current_stage=None,
                external_id=command.external_id,
                external_url=command.external_url,
                created_at=now,
                updated_at=now,
                completed_at=None,
            )

            self._work_items[work_item.id] = work_item
            return work_item

    async def update_work_item(self, command: UpdateWorkItemCommand) -> WorkItem:
        """Updates an existing work item."""
        with self._lock:
            if command.work_item_id not in self._work_items:
                raise WorkItemNotFoundError(command.work_item_id)

            work_item = self._work_items[command.work_item_id]

            # Note: WorkItem domain model doesn't have update methods for title/description
            # These are simple attribute updates that don't require business logic
            if command.title is not None:
                work_item.title = command.title

            if command.description is not None:
                work_item.description = command.description

            # Use domain methods for labels and priority
            if command.labels is not None:
                work_item.update_labels(command.labels)

            if command.priority is not None:
                work_item.update_priority(command.priority)

            work_item.updated_at = datetime.now(UTC)
            return work_item

    async def delete_work_item(self, work_item_id: str) -> WorkItemCommandResult:
        """Soft deletes a work item."""
        with self._lock:
            if work_item_id not in self._work_items:
                raise WorkItemNotFoundError(work_item_id)

            # Remove from storage (in real implementation, this would be a soft delete)
            work_item = self._work_items[work_item_id]
            del self._work_items[work_item_id]

            return WorkItemCommandResult(
                success=True,
                work_item_id=work_item_id,
                message=f"Work item '{work_item.title}' deleted successfully",
                errors=None,
            )

    async def assign_agent(self, command: AssignAgentCommand) -> WorkItem:
        """Assigns an agent to a work item."""
        with self._lock:
            if command.work_item_id not in self._work_items:
                raise WorkItemNotFoundError(command.work_item_id)

            work_item = self._work_items[command.work_item_id]
            # Use domain method for agent assignment
            work_item.assign_agent(command.agent_id, reason="Agent assigned via command")

            return work_item

    async def update_labels(self, command: UpdateLabelsCommand) -> WorkItem:
        """Updates work item labels."""
        with self._lock:
            if command.work_item_id not in self._work_items:
                raise WorkItemNotFoundError(command.work_item_id)

            work_item = self._work_items[command.work_item_id]
            # Use domain method for label updates
            work_item.update_labels(command.labels)

            return work_item

    async def update_priority(self, command: UpdatePriorityCommand) -> WorkItem:
        """Updates work item priority."""
        with self._lock:
            if command.work_item_id not in self._work_items:
                raise WorkItemNotFoundError(command.work_item_id)

            work_item = self._work_items[command.work_item_id]
            # Use domain method for priority updates
            work_item.update_priority(command.priority)

            return work_item

    async def attach_workflow(self, command: AttachWorkflowCommand) -> WorkItem:
        """Attaches a workflow to a work item."""
        with self._lock:
            if command.work_item_id not in self._work_items:
                raise WorkItemNotFoundError(command.work_item_id)

            work_item = self._work_items[command.work_item_id]
            # Note: Direct assignment for current_workflow_id as domain model doesn't enforce validation
            work_item.current_workflow_id = command.workflow_id
            work_item.updated_at = datetime.now(UTC)

            return work_item

    async def update_stage(self, command: UpdateStageCommand) -> WorkItem:
        """Updates work item stage."""
        with self._lock:
            if command.work_item_id not in self._work_items:
                raise WorkItemNotFoundError(command.work_item_id)

            work_item = self._work_items[command.work_item_id]
            # Use domain method for stage updates
            work_item.update_stage(command.stage)

            return work_item

    def get_work_item(self, work_item_id: str) -> WorkItem:
        """Helper method to get a work item (for testing)."""
        with self._lock:
            if work_item_id not in self._work_items:
                raise WorkItemNotFoundError(work_item_id)
            return self._work_items[work_item_id]

    def clear(self):
        """Clear all data (useful for testing)."""
        with self._lock:
            self._work_items.clear()
