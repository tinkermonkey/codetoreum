"""
Mock Workflow Definition Command Adapter

In-memory implementation of IWorkflowDefinitionCommandPort for development and testing.
"""

from threading import RLock
from uuid import uuid4

from codetoreum.ports.input.workflow_definition_command import (
    CreateWorkflowDefinitionCommand,
    DeleteWorkflowDefinitionCommand,
    IWorkflowDefinitionCommandPort,
    UpdateWorkflowDefinitionCommand,
    WorkflowDefinitionCommandResult,
)


class MockWorkflowDefinitionCommandAdapter(IWorkflowDefinitionCommandPort):
    """
    Mock implementation of IWorkflowDefinitionCommandPort using in-memory storage.
    """

    def __init__(self):
        self._workflows: dict[str, dict] = {}
        self._lock = RLock()

    async def create_workflow_definition(
        self, command: CreateWorkflowDefinitionCommand
    ) -> WorkflowDefinitionCommandResult:
        """Create a workflow definition."""
        with self._lock:
            workflow_id = f"wf-{uuid4()}"

            self._workflows[workflow_id] = {
                "name": command.name,
                "project_id": command.project_id,
                "version": 1,
                "is_active": True,
            }

            return WorkflowDefinitionCommandResult(
                success=True,
                workflow_id=workflow_id,
                version=1,
                message=f"Workflow '{command.name}' created successfully",
            )

    async def update_workflow_definition(
        self, command: UpdateWorkflowDefinitionCommand
    ) -> WorkflowDefinitionCommandResult:
        """Update a workflow definition."""
        with self._lock:
            if command.workflow_id in self._workflows:
                workflow = self._workflows[command.workflow_id]
                workflow["version"] = workflow.get("version", 1) + 1

                return WorkflowDefinitionCommandResult(
                    success=True,
                    workflow_id=command.workflow_id,
                    version=workflow["version"],
                    message="Workflow updated successfully",
                )

            return WorkflowDefinitionCommandResult(
                success=False,
                workflow_id=command.workflow_id,
                version=None,
                message="Workflow not found",
            )

    async def delete_workflow_definition(
        self, command: DeleteWorkflowDefinitionCommand
    ) -> WorkflowDefinitionCommandResult:
        """Delete a workflow definition."""
        with self._lock:
            if command.workflow_id in self._workflows:
                del self._workflows[command.workflow_id]

                return WorkflowDefinitionCommandResult(
                    success=True,
                    workflow_id=command.workflow_id,
                    version=None,
                    message="Workflow deleted successfully",
                )

            return WorkflowDefinitionCommandResult(
                success=False,
                workflow_id=command.workflow_id,
                version=None,
                message="Workflow not found",
            )

    async def activate_workflow_definition(self, workflow_id: str) -> WorkflowDefinitionCommandResult:
        """Activate a workflow definition."""
        with self._lock:
            if workflow_id in self._workflows:
                self._workflows[workflow_id]["is_active"] = True

                return WorkflowDefinitionCommandResult(
                    success=True,
                    workflow_id=workflow_id,
                    version=None,
                    message="Workflow activated successfully",
                )

            return WorkflowDefinitionCommandResult(
                success=False,
                workflow_id=workflow_id,
                version=None,
                message="Workflow not found",
            )

    async def deactivate_workflow_definition(self, workflow_id: str) -> WorkflowDefinitionCommandResult:
        """Deactivate a workflow definition."""
        with self._lock:
            if workflow_id in self._workflows:
                self._workflows[workflow_id]["is_active"] = False

                return WorkflowDefinitionCommandResult(
                    success=True,
                    workflow_id=workflow_id,
                    version=None,
                    message="Workflow deactivated successfully",
                )

            return WorkflowDefinitionCommandResult(
                success=False,
                workflow_id=workflow_id,
                version=None,
                message="Workflow not found",
            )

    def clear(self):
        """Clear all data (useful for testing)."""
        with self._lock:
            self._workflows.clear()
