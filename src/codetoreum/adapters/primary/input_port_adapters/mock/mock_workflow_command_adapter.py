"""
Mock Workflow Command Adapter

In-memory implementation of IWorkflowCommandPort for development and testing.
"""

from datetime import UTC, datetime
from threading import RLock
from uuid import uuid4

from codetoreum.ports.input.workflow_command import (
    CancelWorkflowCommand,
    IWorkflowCommandPort,
    PauseWorkflowCommand,
    ResumeWorkflowCommand,
    RetryStageCommand,
    StartWorkflowCommand,
    WorkflowCommandResult,
)


class MockWorkflowCommandAdapter(IWorkflowCommandPort):
    """
    Mock implementation of IWorkflowCommandPort using in-memory storage.
    """

    def __init__(self, workflow_orchestrator=None):
        self._workflows: dict[str, dict] = {}
        self._lock = RLock()
        self._orchestrator = workflow_orchestrator

    async def start_workflow(self, command: StartWorkflowCommand) -> WorkflowCommandResult:
        """Start a workflow."""
        with self._lock:
            workflow_run_id = f"wr-{uuid4()}"

            self._workflows[workflow_run_id] = {
                "work_item_id": command.work_item_id,
                "workflow_id": command.workflow_id,
                "state": "STARTED",
                "started_at": datetime.now(UTC),
            }

            return WorkflowCommandResult(
                success=True,
                workflow_run_id=workflow_run_id,
                message=f"Workflow started for work item {command.work_item_id}",
                state="STARTED",
            )

    async def pause_workflow(self, command: PauseWorkflowCommand) -> WorkflowCommandResult:
        """Pause a workflow."""
        with self._lock:
            if command.workflow_run_id in self._workflows:
                self._workflows[command.workflow_run_id]["state"] = "PAUSED"

            return WorkflowCommandResult(
                success=True,
                workflow_run_id=command.workflow_run_id,
                message="Workflow paused",
                state="PAUSED",
            )

    async def resume_workflow(self, command: ResumeWorkflowCommand) -> WorkflowCommandResult:
        """Resume a workflow."""
        with self._lock:
            if command.workflow_run_id in self._workflows:
                self._workflows[command.workflow_run_id]["state"] = "RESUMED"

            return WorkflowCommandResult(
                success=True,
                workflow_run_id=command.workflow_run_id,
                message="Workflow resumed",
                state="RESUMED",
            )

    async def cancel_workflow(self, command: CancelWorkflowCommand) -> WorkflowCommandResult:
        """Cancel a workflow."""
        with self._lock:
            if command.workflow_run_id in self._workflows:
                self._workflows[command.workflow_run_id]["state"] = "CANCELLED"

            return WorkflowCommandResult(
                success=True,
                workflow_run_id=command.workflow_run_id,
                message="Workflow cancelled",
                state="CANCELLED",
            )

    async def retry_stage(self, command: RetryStageCommand) -> WorkflowCommandResult:
        """Retry a workflow stage."""
        with self._lock:
            if command.workflow_run_id in self._workflows:
                self._workflows[command.workflow_run_id]["state"] = "RETRYING"

            return WorkflowCommandResult(
                success=True,
                workflow_run_id=command.workflow_run_id,
                message=f"Stage {command.stage_name} retried",
                state="STARTED",
            )

    def clear(self):
        """Clear all data (useful for testing)."""
        with self._lock:
            self._workflows.clear()
