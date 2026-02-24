"""
Mock Execution Command Adapter

In-memory implementation of IExecutionCommandPort for development and testing.
"""

from threading import RLock

from codetoreum.domain.agent_execution import AgentExecution
from codetoreum.domain.exceptions import ExecutionNotFoundError, InvalidStateError
from codetoreum.ports.input.execution_command import (
    ExecutionCommandResult,
    IExecutionCommandPort,
    PauseExecutionCommand,
    ResumeExecutionCommand,
    TerminateExecutionCommand,
)


class MockExecutionCommandAdapter(IExecutionCommandPort):
    """
    Mock implementation of IExecutionCommandPort using in-memory storage.
    """

    def __init__(self):
        self._executions: dict[str, AgentExecution] = {}
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
                raise ExecutionNotFoundError(command.execution_id)

            execution = self._executions[command.execution_id]

            # Check if execution is already in a terminal state
            if execution.is_terminal():
                raise InvalidStateError(
                    f"Execution {command.execution_id} is already {execution.status.value}"
                )

            # Use domain method to cancel execution
            execution.cancel(command.reason)

            return ExecutionCommandResult(
                success=True,
                execution_id=command.execution_id,
                message=f"Execution terminated: {command.reason or 'No reason provided'}",
                new_status=execution.status.value,
                errors=None,
            )

    async def pause_execution(
        self, command: PauseExecutionCommand
    ) -> ExecutionCommandResult:
        """Pause a running execution."""
        with self._lock:
            if command.execution_id not in self._executions:
                raise ExecutionNotFoundError(command.execution_id)

            execution = self._executions[command.execution_id]

            # Use domain method to pause execution (it handles validation)
            try:
                execution.pause(command.reason)
            except Exception as e:
                raise InvalidStateError(str(e))

            return ExecutionCommandResult(
                success=True,
                execution_id=command.execution_id,
                message="Execution paused successfully",
                new_status=execution.status.value,
                errors=None,
            )

    async def resume_execution(
        self, command: ResumeExecutionCommand
    ) -> ExecutionCommandResult:
        """Resume a paused execution."""
        with self._lock:
            if command.execution_id not in self._executions:
                raise ExecutionNotFoundError(command.execution_id)

            execution = self._executions[command.execution_id]

            # Use domain method to resume execution (it handles validation)
            try:
                execution.resume()
            except Exception as e:
                raise InvalidStateError(str(e))

            return ExecutionCommandResult(
                success=True,
                execution_id=command.execution_id,
                message="Execution resumed successfully",
                new_status=execution.status.value,
                errors=None,
            )

    def get_execution(self, execution_id: str) -> AgentExecution:
        """Helper method to get an execution (for testing)."""
        with self._lock:
            if execution_id not in self._executions:
                raise ExecutionNotFoundError(execution_id)
            return self._executions[execution_id]

    def clear(self):
        """Clear all data (useful for testing)."""
        with self._lock:
            self._executions.clear()
