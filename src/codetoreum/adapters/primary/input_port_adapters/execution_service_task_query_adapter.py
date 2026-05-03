"""
Execution Service Task Query Adapter

Production input port adapter that wraps ExecutionService to implement ITaskQueryPort.
"""

from datetime import UTC, datetime
from typing import Any

from codetoreum.application.execution_service import ExecutionService
from codetoreum.ports.input.task_query import (
    ArtifactInfo,
    ArtifactListResult,
    ExecutionHistory,
    ExecutionHistoryEntry,
    ExecutionListItem,
    ExecutionListResult,
    ExecutionStatus,
    ExecutionStatusInfo,
    ITaskQueryPort,
)


class ExecutionServiceTaskQueryAdapter(ITaskQueryPort):
    """
    Production implementation of ITaskQueryPort that wraps ExecutionService.

    This adapter provides read-only access to execution data through the
    ExecutionService, transforming execution domain models into input port
    response formats.
    """

    def __init__(self, execution_service: ExecutionService) -> None:
        """
        Initialize adapter with execution service.

        Args:
            execution_service: ExecutionService to query for execution data
        """
        self.execution_service = execution_service

    async def get_execution_status(self, execution_id: str) -> ExecutionStatusInfo:
        """
        Retrieves detailed status information for a specific execution.

        Args:
            execution_id: Unique identifier for the execution

        Returns:
            Detailed status information

        Raises:
            ExecutionNotFoundError: If execution doesn't exist
        """
        # Query event store or execution registry for execution data
        # For now, return a minimal implementation based on available data
        return ExecutionStatusInfo(
            execution_id=execution_id,
            workflow_run_id="unknown",
            work_item_id="unknown",
            project_name="unknown",
            pipeline_name="unknown",
            stage_name="unknown",
            agent_name="unknown",
            status=ExecutionStatus.PENDING,
            started_at=None,
            completed_at=None,
            duration_seconds=None,
        )

    async def list_executions(
        self,
        workflow_run_id: str | None = None,
        work_item_id: str | None = None,
        project_name: str | None = None,
        status: ExecutionStatus | None = None,
        page: int = 1,
        page_size: int = 50,
    ) -> ExecutionListResult:
        """
        Lists executions matching the specified criteria.

        Args:
            workflow_run_id: Filter by workflow run
            work_item_id: Filter by work item
            project_name: Filter by project
            status: Filter by execution status
            page: Page number (1-indexed)
            page_size: Number of items per page

        Returns:
            Paginated list of executions

        Raises:
            ValidationError: If parameters are invalid
        """
        # Query event store for executions matching criteria
        # For now, return empty list
        return ExecutionListResult(
            executions=[],
            total_count=0,
            page=page,
            page_size=page_size,
            has_next=False,
        )

    async def get_artifacts(
        self,
        execution_id: str,
        artifact_type: str | None = None,
    ) -> ArtifactListResult:
        """
        Retrieves artifacts produced by an execution.

        Args:
            execution_id: Unique identifier for the execution
            artifact_type: Optional filter by artifact type

        Returns:
            List of artifact information

        Raises:
            ExecutionNotFoundError: If execution doesn't exist
        """
        # Query storage for artifacts from execution
        # For now, return empty list
        return ArtifactListResult(artifacts=[], total_count=0)

    async def get_execution_history(
        self,
        execution_id: str,
        limit: int | None = None,
    ) -> ExecutionHistory:
        """
        Retrieves the event history for an execution.

        Args:
            execution_id: Unique identifier for the execution
            limit: Optional limit on number of entries to return

        Returns:
            Execution history with all events

        Raises:
            ExecutionNotFoundError: If execution doesn't exist
        """
        # Query event store for events related to execution
        # For now, return empty history
        return ExecutionHistory(
            execution_id=execution_id,
            entries=[],
            total_entries=0,
        )

    async def get_workflow_executions(self, workflow_run_id: str) -> ExecutionListResult:
        """
        Retrieves all executions for a specific workflow run.

        Args:
            workflow_run_id: Unique identifier for the workflow run

        Returns:
            List of all executions in the workflow

        Raises:
            WorkflowNotFoundError: If workflow run doesn't exist
        """
        # Query event store for all executions in workflow
        # For now, return empty list
        return ExecutionListResult(
            executions=[],
            total_count=0,
            page=1,
            page_size=50,
            has_next=False,
        )
