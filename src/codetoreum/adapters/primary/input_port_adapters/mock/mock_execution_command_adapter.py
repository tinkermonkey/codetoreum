"""
Mock Execution Command Adapter

In-memory implementation of IExecutionCommandPort for development and testing.
"""

from datetime import datetime, timezone
from typing import Dict
from threading import RLock

from codetoreum.ports.input.execution_command import (
    ExecutionCommandResult,
    IExecutionCommandPort,
    PauseExecutionCommand,
    ResumeExecutionCommand,
    TerminateExecutionCommand,
)
from codetoreum.domain.agent_execution import AgentExecution, ExecutionStatus
from codetoreum.domain.exceptions import ExecutionNotFoundError, InvalidStateError


class MockExecutionCommandAdapter(IExecutionCommandPort):
    """
    Mock implementation of IExecutionCommandPort using in-memory storage.
    """

    def __init__(self):
        self._executions: Dict[str, AgentExecution] = {}
        self._lock = RLock()

    def add_execution(self, execution: AgentExecution):
        """Helper method to add an execution to mock storage."""
        with self._lock:
            self._executions[execution.id] = execution

    async def terminate_execution(
        self, command: TerminateExecutionCommand
    ) -> ExecutionCommandResult:
        """Terminate a running execution."""
        with self._lock:
            if command.execution_id not in self._executions:
                raise ExecutionNotFoundError(
                    f"Execution with ID {command.execution_id} not found"
                )

            execution = self._executions[command.execution_id]

            # Check if execution is already completed
            if execution.status in [ExecutionStatus.COMPLETED, ExecutionStatus.FAILED]:
                raise InvalidStateError(
                    f"Execution {command.execution_id} is already {execution.status.value}"
                )

            # Simulate termination
            execution._status = ExecutionStatus.TERMINATED
            execution._completed_at = datetime.now(timezone.utc)

            return ExecutionCommandResult(
                success=True,
                execution_id=command.execution_id,
                message=f"Execution terminated: {command.reason or 'No reason provided'}",
                new_status=ExecutionStatus.TERMINATED.value,
                errors=None,
            )

    async def pause_execution(
        self, command: PauseExecutionCommand
    ) -> ExecutionCommandResult:
        """Pause a running execution."""
        with self._lock:
            if command.execution_id not in self._executions:
                raise ExecutionNotFoundError(
                    f"Execution with ID {command.execution_id} not found"
                )

            execution = self._executions[command.execution_id]

            # Check if execution can be paused
            if execution.status != ExecutionStatus.RUNNING:
                raise InvalidStateError(
                    f"Execution {command.execution_id} cannot be paused (current status: {execution.status.value})"
                )

            # Simulate pause
            execution._status = ExecutionStatus.PAUSED

            return ExecutionCommandResult(
                success=True,
                execution_id=command.execution_id,
                message="Execution paused successfully",
                new_status=ExecutionStatus.PAUSED.value,
                errors=None,
            )

    async def resume_execution(
        self, command: ResumeExecutionCommand
    ) -> ExecutionCommandResult:
        """Resume a paused execution."""
        with self._lock:
            if command.execution_id not in self._executions:
                raise ExecutionNotFoundError(
                    f"Execution with ID {command.execution_id} not found"
                )

            execution = self._executions[command.execution_id]

            # Check if execution is paused
            if execution.status != ExecutionStatus.PAUSED:
                raise InvalidStateError(
                    f"Execution {command.execution_id} is not paused (current status: {execution.status.value})"
                )

            # Simulate resume
            execution._status = ExecutionStatus.RUNNING

            return ExecutionCommandResult(
                success=True,
                execution_id=command.execution_id,
                message="Execution resumed successfully",
                new_status=ExecutionStatus.RUNNING.value,
                errors=None,
            )

    def get_execution(self, execution_id: str) -> AgentExecution:
        """Helper method to get an execution (for testing)."""
        with self._lock:
            if execution_id not in self._executions:
                raise ExecutionNotFoundError(f"Execution with ID {execution_id} not found")
            return self._executions[execution_id]

    def clear(self):
        """Clear all data (useful for testing)."""
        with self._lock:
            self._executions.clear()
