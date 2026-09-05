"""
Workflow Command Input Port

This module defines the input port interface for workflow command operations,
including starting, pausing, resuming, canceling, and retrying workflows.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class TriggerType(Enum):
    """Type of workflow trigger"""

    CARD_MOVEMENT = "card_movement"
    MANUAL = "manual"
    SCHEDULED = "scheduled"
    API = "api"
    AGENT_FEEDBACK = "agent_feedback"


@dataclass
class StartWorkflowCommand:
    """Command to start a new workflow execution"""

    project_name: str
    work_item_id: str  # Issue number, discussion ID, etc.
    pipeline_name: str
    stage_name: str | None = None  # If None, start from first stage
    trigger: TriggerType = TriggerType.MANUAL
    context: dict[str, Any] | None = None
    priority: str = "MEDIUM"  # LOW, MEDIUM, HIGH, CRITICAL


@dataclass
class PauseWorkflowCommand:
    """Command to pause an active workflow"""

    workflow_run_id: str
    reason: str
    pause_point: str  # Current stage to pause at


@dataclass
class ResumeWorkflowCommand:
    """Command to resume a paused workflow"""

    workflow_run_id: str
    from_stage: str | None = None  # If None, resume from paused point


@dataclass
class CancelWorkflowCommand:
    """Command to cancel a workflow"""

    workflow_run_id: str
    reason: str
    force: bool = False  # If True, immediate cancellation


@dataclass
class RetryStageCommand:
    """Command to retry a failed stage"""

    workflow_run_id: str
    stage_name: str
    reset_state: bool = True  # If True, clear previous attempts


@dataclass
class WorkflowCommandResult:
    """Result of executing a workflow command"""

    success: bool
    workflow_run_id: str
    message: str
    state: str  # STARTED, PAUSED, RESUMED, CANCELLED, COMPLETED
    errors: list[str] | None = field(default=None)


class IWorkflowCommandPort(ABC):
    """
    Input port for workflow commands.

    This port accepts commands to control workflow execution lifecycle,
    including starting, pausing, resuming, and canceling workflows.

    Implementations of this port should:
    - Validate command parameters
    - Delegate to application services for execution
    - Emit appropriate domain events
    - Handle errors and return results
    """

    @abstractmethod
    async def start_workflow(self, command: StartWorkflowCommand) -> WorkflowCommandResult:
        """
        Starts a new workflow execution.

        Args: command: Command with workflow execution parameters

        Returns: Result containing workflow run ID and status

        Raises: ProjectNotFoundError: If project doesn't exist
            PipelineNotFoundError: If pipeline doesn't exist
            WorkItemNotFoundError: If work item doesn't exist
            ValidationError: If command parameters invalid
        """

    @abstractmethod
    async def pause_workflow(self, command: PauseWorkflowCommand) -> WorkflowCommandResult:
        """
        Pauses an active workflow execution.

        Args: command: Command with pause parameters

        Returns: Result containing updated workflow status

        Raises: WorkflowNotFoundError: If workflow doesn't exist
            WorkflowNotActiveError: If workflow not in active state
        """

    @abstractmethod
    async def resume_workflow(self, command: ResumeWorkflowCommand) -> WorkflowCommandResult:
        """
        Resumes a paused workflow execution.

        Args: command: Command with resume parameters

        Returns: Result containing updated workflow status

        Raises: WorkflowNotFoundError: If workflow doesn't exist
            WorkflowNotPausedError: If workflow not in paused state
        """

    @abstractmethod
    async def cancel_workflow(self, command: CancelWorkflowCommand) -> WorkflowCommandResult:
        """
        Cancels a workflow execution.

        Args: command: Command with cancellation parameters

        Returns: Result containing final workflow status

        Raises: WorkflowNotFoundError: If workflow doesn't exist
        """

    @abstractmethod
    async def retry_stage(self, command: RetryStageCommand) -> WorkflowCommandResult:
        """
        Retries a failed workflow stage.

        Args: command: Command with retry parameters

        Returns: Result containing updated workflow status

        Raises: WorkflowNotFoundError: If workflow doesn't exist
            StageNotFoundError: If stage doesn't exist
        """
