"""
Mock Work Item Command Adapter

In-memory implementation of IWorkItemCommandPort for development and testing.
"""

from datetime import datetime, timezone
from typing import Dict
from threading import RLock
from uuid import uuid4

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
from codetoreum.domain.work_item import WorkItem, WorkItemStatus
from codetoreum.domain.exceptions import WorkItemNotFoundError, DomainError


class MockWorkItemCommandAdapter(IWorkItemCommandPort):
    """
    Mock implementation of IWorkItemCommandPort using in-memory storage.
    """

    def __init__(self):
        self._work_items: Dict[str, WorkItem] = {}
        self._lock = RLock()

    async def create_work_item(self, command: CreateWorkItemCommand) -> WorkItem:
        """Creates a new work item."""
        with self._lock:
            work_item_id = str(uuid4())
            now = datetime.now(timezone.utc)

            work_item = WorkItem(
                id=work_item_id,
                project_id=command.project_id,
                title=command.title,
                description=command.description,
                status=WorkItemStatus.OPEN,
                priority=command.priority,
                assignee=None,
                labels=command.labels or [],
                workflow_id=None,
                workflow_stage=None,
                external_id=command.external_id,
                external_url=command.external_url,
                metadata={},
                created_at=now,
                updated_at=now,
            )

            self._work_items[work_item_id] = work_item
            return work_item

    async def update_work_item(self, command: UpdateWorkItemCommand) -> WorkItem:
        """Updates an existing work item."""
        with self._lock:
            if command.work_item_id not in self._work_items:
                raise WorkItemNotFoundError(
                    f"Work item with ID {command.work_item_id} not found"
                )

            work_item = self._work_items[command.work_item_id]

            if command.title is not None:
                work_item.title = command.title

            if command.description is not None:
                work_item.description = command.description

            if command.labels is not None:
                work_item.labels = command.labels

            if command.priority is not None:
                work_item.priority = command.priority

            work_item.updated_at = datetime.now(timezone.utc)
            return work_item

    async def delete_work_item(self, work_item_id: str) -> WorkItemCommandResult:
        """Soft deletes a work item."""
        with self._lock:
            if work_item_id not in self._work_items:
                raise WorkItemNotFoundError(f"Work item with ID {work_item_id} not found")

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
                raise WorkItemNotFoundError(
                    f"Work item with ID {command.work_item_id} not found"
                )

            work_item = self._work_items[command.work_item_id]
            work_item.assignee = command.agent_id
            work_item.updated_at = datetime.now(timezone.utc)

            return work_item

    async def update_labels(self, command: UpdateLabelsCommand) -> WorkItem:
        """Updates work item labels."""
        with self._lock:
            if command.work_item_id not in self._work_items:
                raise WorkItemNotFoundError(
                    f"Work item with ID {command.work_item_id} not found"
                )

            work_item = self._work_items[command.work_item_id]
            work_item.labels = command.labels
            work_item.updated_at = datetime.now(timezone.utc)

            return work_item

    async def update_priority(self, command: UpdatePriorityCommand) -> WorkItem:
        """Updates work item priority."""
        with self._lock:
            if command.work_item_id not in self._work_items:
                raise WorkItemNotFoundError(
                    f"Work item with ID {command.work_item_id} not found"
                )

            work_item = self._work_items[command.work_item_id]
            work_item.priority = command.priority
            work_item.updated_at = datetime.now(timezone.utc)

            return work_item

    async def attach_workflow(self, command: AttachWorkflowCommand) -> WorkItem:
        """Attaches a workflow to a work item."""
        with self._lock:
            if command.work_item_id not in self._work_items:
                raise WorkItemNotFoundError(
                    f"Work item with ID {command.work_item_id} not found"
                )

            work_item = self._work_items[command.work_item_id]
            work_item.workflow_id = command.workflow_id
            work_item.updated_at = datetime.now(timezone.utc)

            return work_item

    async def update_stage(self, command: UpdateStageCommand) -> WorkItem:
        """Updates work item stage."""
        with self._lock:
            if command.work_item_id not in self._work_items:
                raise WorkItemNotFoundError(
                    f"Work item with ID {command.work_item_id} not found"
                )

            work_item = self._work_items[command.work_item_id]
            work_item.workflow_stage = command.stage
            work_item.updated_at = datetime.now(timezone.utc)

            return work_item

    def get_work_item(self, work_item_id: str) -> WorkItem:
        """Helper method to get a work item (for testing)."""
        with self._lock:
            if work_item_id not in self._work_items:
                raise WorkItemNotFoundError(f"Work item with ID {work_item_id} not found")
            return self._work_items[work_item_id]

    def clear(self):
        """Clear all data (useful for testing)."""
        with self._lock:
            self._work_items.clear()
