"""
Orchestration Command Input Port

This module defines the input port interface for orchestration command operations,
including starting, pausing, resuming, and canceling workflow executions.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional


class ExecutionPriority(Enum):
    """Execution priority levels"""
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


@dataclass
class StartExecutionCommand:
    """Command to start a workflow execution"""
    work_item_id: str
    workflow_id: str
    stage_name: Optional[str] = None  # If None, start from first stage
    priority: ExecutionPriority = ExecutionPriority.MEDIUM
    context: Dict[str, Any] = field(default_factory=dict)


@dataclass
class CancelExecutionCommand:
    """Command to cancel a workflow execution"""
    workflow_run_id: str
    reason: str
    force: bool = False  # If True, immediate cancellation without cleanup


@dataclass
class PauseExecutionCommand:
    """Command to pause a workflow execution"""
    workflow_run_id: str
    reason: str


@dataclass
class ResumeExecutionCommand:
    """Command to resume a paused workflow execution"""
    workflow_run_id: str
    from_stage: Optional[str] = None  # If None, resume from paused stage


@dataclass
class OrchestrationCommandResult:
    """Result of executing an orchestration command"""
    success: bool
    execution_id: str
    workflow_run_id: str
    status: str  # ACCEPTED, STARTED, PAUSED, RESUMED, CANCELLED
    message: str
    started_at: Optional[datetime] = None
    errors: Optional[List[str]] = field(default=None)


@dataclass
class EntryConditionCheckResult:
    """Result of checking entry conditions"""
    can_start: bool
    stage_name: str
    blocking_conditions: List[str]
    condition_details: List[Dict[str, Any]]


class IOrchestrationCommandPort(ABC):
    """
    Input port for orchestration commands.

    This port accepts commands to control workflow execution at a high level,
    coordinating between the workflow orchestrator and agent scheduler.

    Implementations of this port should:
    - Validate command parameters
    - Check entry conditions before starting workflows
    - Delegate to WorkflowOrchestrator for execution control
    - Emit appropriate domain events
    - Handle errors and return results
    """

    @abstractmethod
    async def start_execution(
        self,
        command: StartExecutionCommand
    ) -> OrchestrationCommandResult:
        """
        Starts a new workflow execution for a work item.

        This operation:
        1. Validates workflow and work item exist
        2. Checks entry conditions for the starting stage
        3. Creates a workflow run
        4. Queues the first agent execution
        5. Emits WorkflowStarted event

        Args:
            command: Command with execution parameters

        Returns:
            Result containing execution ID and initial status

        Raises:
            WorkflowNotFoundError: If workflow doesn't exist
            WorkItemNotFoundError: If work item doesn't exist
            EntryConditionNotMetError: If entry conditions not satisfied
            ValidationError: If command parameters invalid
        """
        pass

    @abstractmethod
    async def cancel_execution(
        self,
        command: CancelExecutionCommand
    ) -> OrchestrationCommandResult:
        """
        Cancels an active workflow execution.

        If force=False (default):
        - Current agent execution completes gracefully
        - No new executions are started
        - Cleanup tasks run

        If force=True:
        - Current agent execution is terminated immediately
        - Cleanup tasks may not run

        Args:
            command: Command with cancellation parameters

        Returns:
            Result containing updated workflow status

        Raises:
            WorkflowNotFoundError: If workflow run doesn't exist
        """
        pass

    @abstractmethod
    async def pause_execution(
        self,
        command: PauseExecutionCommand
    ) -> OrchestrationCommandResult:
        """
        Pauses an active workflow execution.

        Current agent execution completes, but no new executions are started
        until the workflow is resumed.

        Args:
            command: Command with pause parameters

        Returns:
            Result containing updated workflow status

        Raises:
            WorkflowNotFoundError: If workflow run doesn't exist
            WorkflowNotActiveError: If workflow not in active state
        """
        pass

    @abstractmethod
    async def resume_execution(
        self,
        command: ResumeExecutionCommand
    ) -> OrchestrationCommandResult:
        """
        Resumes a paused workflow execution.

        Workflow continues from the stage it was paused at (or a specified stage).

        Args:
            command: Command with resume parameters

        Returns:
            Result containing updated workflow status

        Raises:
            WorkflowNotFoundError: If workflow run doesn't exist
            WorkflowNotPausedError: If workflow not in paused state
        """
        pass

    @abstractmethod
    async def check_entry_conditions(
        self,
        work_item_id: str,
        workflow_id: str,
        stage_name: Optional[str] = None
    ) -> EntryConditionCheckResult:
        """
        Checks whether entry conditions are met for starting a workflow.

        This is called internally before starting a workflow, but can also
        be called externally to validate before attempting to start.

        Args:
            work_item_id: Work item to check
            workflow_id: Workflow to check conditions for
            stage_name: Specific stage to check (defaults to first stage)

        Returns:
            Result indicating whether conditions are met and details

        Raises:
            WorkflowNotFoundError: If workflow doesn't exist
            WorkItemNotFoundError: If work item doesn't exist
        """
        pass
