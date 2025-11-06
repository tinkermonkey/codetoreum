"""
Mock Orchestration Command Adapter

In-memory implementation of IOrchestrationCommandPort for development and testing.
"""

from datetime import datetime, timezone
from typing import Dict, Optional
from threading import RLock
from uuid import uuid4

from codetoreum.ports.input.orchestration_command import (
    IOrchestrationCommandPort,
    StartExecutionCommand,
    CancelExecutionCommand,
    PauseExecutionCommand,
    ResumeExecutionCommand,
    OrchestrationCommandResult,
    EntryConditionCheckResult,
)


class MockOrchestrationCommandAdapter(IOrchestrationCommandPort):
    """
    Mock implementation of IOrchestrationCommandPort using in-memory storage.
    """

    def __init__(self):
        self._executions: Dict[str, Dict] = {}
        self._lock = RLock()

    async def start_execution(self, command: StartExecutionCommand) -> OrchestrationCommandResult:
        """Start an execution."""
        with self._lock:
            execution_id = f"exec-{uuid4()}"
            workflow_run_id = f"wr-{uuid4()}"

            self._executions[execution_id] = {
                "work_item_id": command.work_item_id,
                "workflow_id": command.workflow_id,
                "status": "ACCEPTED",
                "started_at": datetime.now(timezone.utc),
            }

            return OrchestrationCommandResult(
                success=True,
                execution_id=execution_id,
                workflow_run_id=workflow_run_id,
                status="ACCEPTED",
                message=f"Execution started for work item {command.work_item_id}",
                started_at=datetime.now(timezone.utc),
            )

    async def cancel_execution(self, command: CancelExecutionCommand) -> OrchestrationCommandResult:
        """Cancel an execution."""
        with self._lock:
            if command.execution_id in self._executions:
                self._executions[command.execution_id]["status"] = "CANCELLED"

            return OrchestrationCommandResult(
                success=True,
                execution_id=command.execution_id,
                workflow_run_id=command.workflow_run_id,
                status="CANCELLED",
                message="Execution cancelled",
            )

    async def pause_execution(self, command: PauseExecutionCommand) -> OrchestrationCommandResult:
        """Pause an execution."""
        with self._lock:
            if command.execution_id in self._executions:
                self._executions[command.execution_id]["status"] = "PAUSED"

            return OrchestrationCommandResult(
                success=True,
                execution_id=command.execution_id,
                workflow_run_id=command.workflow_run_id,
                status="PAUSED",
                message="Execution paused",
            )

    async def resume_execution(self, command: ResumeExecutionCommand) -> OrchestrationCommandResult:
        """Resume an execution."""
        with self._lock:
            if command.execution_id in self._executions:
                self._executions[command.execution_id]["status"] = "RESUMED"

            return OrchestrationCommandResult(
                success=True,
                execution_id=command.execution_id,
                workflow_run_id=command.workflow_run_id,
                status="RESUMED",
                message="Execution resumed",
            )

    async def check_entry_conditions(
        self,
        work_item_id: str,
        workflow_id: str,
        stage_name: Optional[str] = None,
    ) -> EntryConditionCheckResult:
        """Check entry conditions for a workflow stage."""
        return EntryConditionCheckResult(
            can_start=True,
            stage_name=stage_name or "development",
            blocking_conditions=[],
            condition_details=[],
        )

    def clear(self):
        """Clear all data (useful for testing)."""
        with self._lock:
            self._executions.clear()
