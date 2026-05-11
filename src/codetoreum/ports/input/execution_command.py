"""
Execution Command Port Interface

Defines the contract for execution command operations.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass

# ============================================================================
# Commands
# ============================================================================


@dataclass
class TerminateExecutionCommand:
    """Command to terminate a running execution."""

    execution_id: str
    reason: str | None = None


@dataclass
class PauseExecutionCommand:
    """Command to pause a running execution."""

    execution_id: str


@dataclass
class ResumeExecutionCommand:
    """Command to resume a paused execution."""

    execution_id: str


# ============================================================================
# Result Models
# ============================================================================


@dataclass
class ExecutionCommandResult:
    """Result from execution command operations."""

    success: bool
    execution_id: str
    message: str
    new_status: str | None = None
    errors: list | None = None


# ============================================================================
# Port Interface
# ============================================================================


class IExecutionCommandPort(ABC):
    """
    Execution Command Input Port.

    Provides write operations for execution lifecycle management.
    """

    @abstractmethod
    async def terminate_execution(self, command: TerminateExecutionCommand) -> ExecutionCommandResult:
        """
        Terminate a running execution.

        This triggers:
        - Container termination
        - Workspace cleanup
        - Domain event emission

        Args: command: TerminateExecutionCommand with execution ID and reason

        Returns: ExecutionCommandResult with operation status

        Raises: ExecutionNotFoundError: If execution doesn't exist
            InvalidStateError: If execution is already completed (409 Conflict)
        """

    @abstractmethod
    async def pause_execution(self, command: PauseExecutionCommand) -> ExecutionCommandResult:
        """
        Pause a running execution.

        Args: command: PauseExecutionCommand with execution ID

        Returns: ExecutionCommandResult with operation status

        Raises: ExecutionNotFoundError: If execution doesn't exist
            InvalidStateError: If execution cannot be paused
        """

    @abstractmethod
    async def resume_execution(self, command: ResumeExecutionCommand) -> ExecutionCommandResult:
        """
        Resume a paused execution.

        Args: command: ResumeExecutionCommand with execution ID

        Returns: ExecutionCommandResult with operation status

        Raises: ExecutionNotFoundError: If execution doesn't exist
            InvalidStateError: If execution is not paused
        """
