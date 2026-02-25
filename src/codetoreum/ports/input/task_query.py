"""
Task Query Input Port

This module defines the input port interface for querying task and execution information,
including status, history, artifacts, and results.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any


class ExecutionStatus(Enum):
    """Status of an execution"""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    PAUSED = "paused"


@dataclass
class ExecutionStatusInfo:
    """Detailed status information for an execution"""
    execution_id: str
    workflow_run_id: str
    work_item_id: str
    project_name: str
    pipeline_name: str
    stage_name: str
    agent_name: str
    status: ExecutionStatus
    started_at: datetime | None = None
    completed_at: datetime | None = None
    duration_seconds: float | None = None
    error_message: str | None = None
    retry_count: int = 0
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class ExecutionListItem:
    """Summary information for execution in a list"""
    execution_id: str
    workflow_run_id: str
    work_item_id: str
    stage_name: str
    agent_name: str
    status: ExecutionStatus
    started_at: datetime | None = None
    duration_seconds: float | None = None


@dataclass
class ExecutionListResult:
    """Result of listing executions"""
    executions: list[ExecutionListItem]
    total_count: int
    page: int
    page_size: int
    has_next: bool


@dataclass
class ArtifactInfo:
    """Information about an execution artifact"""
    artifact_id: str
    execution_id: str
    artifact_type: str  # code, log, report, diagram, etc.
    name: str
    path: str
    size_bytes: int
    created_at: datetime
    mime_type: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class ArtifactListResult:
    """Result of listing artifacts"""
    artifacts: list[ArtifactInfo]
    total_count: int


@dataclass
class ExecutionHistoryEntry:
    """Single entry in execution history"""
    timestamp: datetime
    event_type: str
    message: str
    details: dict[str, Any] | None = None


@dataclass
class ExecutionHistory:
    """Complete execution history"""
    execution_id: str
    entries: list[ExecutionHistoryEntry]
    total_entries: int


class ITaskQueryPort(ABC):
    """
    Input port for task and execution queries.

    This port provides read-only access to execution status, history,
    artifacts, and related information.

    Implementations of this port should:
    - Query read models or event store for execution data
    - Transform data into appropriate response formats
    - Handle pagination for large result sets
    - Support filtering and sorting
    """

    @abstractmethod
    async def get_execution_status(
        self,
        execution_id: str
    ) -> ExecutionStatusInfo:
        """
        Retrieves detailed status information for a specific execution.

        Args:
            execution_id: Unique identifier for the execution

        Returns:
            Detailed status information

        Raises:
            ExecutionNotFoundError: If execution doesn't exist
        """

    @abstractmethod
    async def list_executions(
        self,
        workflow_run_id: str | None = None,
        work_item_id: str | None = None,
        project_name: str | None = None,
        status: ExecutionStatus | None = None,
        page: int = 1,
        page_size: int = 50
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

    @abstractmethod
    async def get_artifacts(
        self,
        execution_id: str,
        artifact_type: str | None = None
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

    @abstractmethod
    async def get_execution_history(
        self,
        execution_id: str,
        limit: int | None = None
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

    @abstractmethod
    async def get_workflow_executions(
        self,
        workflow_run_id: str
    ) -> ExecutionListResult:
        """
        Retrieves all executions for a specific workflow run.

        Args:
            workflow_run_id: Unique identifier for the workflow run

        Returns:
            List of all executions in the workflow

        Raises:
            WorkflowNotFoundError: If workflow run doesn't exist
        """
