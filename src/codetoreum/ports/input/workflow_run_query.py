"""
Workflow Run Query Input Port

This module defines the input port interface for workflow run query operations,
including retrieving workflow execution runs, their status, and events.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import List, Optional


class WorkflowRunStatus(Enum):
    """Status enumeration for workflow runs"""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class WorkflowRunSortField(Enum):
    """Fields available for sorting workflow run lists"""
    STARTED_AT = "startedAt"
    COMPLETED_AT = "completedAt"
    DURATION = "duration"


class SortOrder(Enum):
    """Sort order"""
    ASC = "asc"
    DESC = "desc"


@dataclass
class WorkflowRunFilters:
    """Filters for listing workflow runs"""
    status: Optional[List[WorkflowRunStatus]] = None  # Filter by status (comma-separated)
    project_id: Optional[str] = None  # Filter by project
    work_item_id: Optional[str] = None  # Filter by work item
    workflow_id: Optional[str] = None  # Filter by workflow template


@dataclass
class WorkflowRunPaginationParams:
    """Pagination parameters for workflow run queries"""
    offset: int = 0
    limit: int = 20
    sort_by: WorkflowRunSortField = WorkflowRunSortField.STARTED_AT
    sort_order: SortOrder = SortOrder.DESC


@dataclass
class WorkflowRunStageInfo:
    """Information about a workflow run stage"""
    name: str
    agent_name: str
    status: str  # pending, running, completed, failed
    started_at: Optional[datetime]
    completed_at: Optional[datetime]
    execution_id: Optional[str]


@dataclass
class WorkflowRunInfo:
    """Complete workflow run information"""
    id: str
    work_item_id: str
    workflow_id: str
    project_id: str
    status: WorkflowRunStatus
    current_stage_index: int
    current_stage_name: Optional[str]
    stages: List[WorkflowRunStageInfo]
    started_at: Optional[datetime]
    completed_at: Optional[datetime]
    duration: Optional[int]  # Duration in seconds
    issue_title: Optional[str]
    issue_number: Optional[int]
    project: Optional[str]
    triggered_by: Optional[str]
    priority: Optional[str]
    metadata: dict


@dataclass
class WorkflowRunSummary:
    """Summary information for workflow run list"""
    id: str
    work_item_id: str
    workflow_id: str
    project_id: str
    status: WorkflowRunStatus
    current_stage_index: int
    current_stage_name: Optional[str]
    started_at: Optional[datetime]
    completed_at: Optional[datetime]
    duration: Optional[int]
    issue_title: Optional[str]
    issue_number: Optional[int]
    project: Optional[str]
    triggered_by: Optional[str]
    priority: Optional[str]


@dataclass
class WorkflowRunListResult:
    """Result of listing workflow runs"""
    runs: List[WorkflowRunSummary]
    total_count: int
    offset: int
    limit: int
    has_next: bool


class IWorkflowRunQueryPort(ABC):
    """
    Input port for workflow run queries.

    This port provides read-only access to workflow execution runs, including
    retrieving individual runs, listing with filters, and querying run status.

    Implementations of this port should:
    - Query workflow execution storage for runs
    - Transform data into appropriate response formats
    - Handle pagination for large result sets
    - Support filtering and sorting
    """

    @abstractmethod
    async def get_workflow_run(
        self,
        workflow_run_id: str
    ) -> WorkflowRunInfo:
        """
        Retrieves a workflow run by ID.

        Args:
            workflow_run_id: Unique identifier for the workflow run

        Returns:
            Complete workflow run information

        Raises:
            WorkflowRunNotFoundError: If workflow run doesn't exist
        """
        pass

    @abstractmethod
    async def list_workflow_runs(
        self,
        filters: Optional[WorkflowRunFilters] = None,
        pagination: Optional[WorkflowRunPaginationParams] = None
    ) -> WorkflowRunListResult:
        """
        Lists workflow runs matching the specified criteria.

        Args:
            filters: Optional filters to apply
            pagination: Pagination parameters

        Returns:
            Paginated list of workflow run summaries

        Raises:
            ValidationError: If parameters are invalid
        """
        pass

    @abstractmethod
    async def get_workflow_run_events(
        self,
        workflow_run_id: str,
        offset: int = 0,
        limit: int = 50,
        event_types: Optional[List[str]] = None,
        since: Optional[datetime] = None
    ) -> dict:
        """
        Retrieves events for a specific workflow run.

        Args:
            workflow_run_id: Unique identifier for the workflow run
            offset: Pagination offset
            limit: Pagination limit (default 50, max 200)
            event_types: Optional filter by event types (comma-separated)
            since: Optional ISO timestamp - events after this time

        Returns:
            Dictionary containing events list and pagination info

        Raises:
            WorkflowRunNotFoundError: If workflow run doesn't exist
        """
        pass

    @abstractmethod
    async def get_workflow_run_audit(
        self,
        workflow_run_id: str,
        offset: int = 0,
        limit: int = 100,
    ) -> dict:
        """
        Retrieves comprehensive audit information for a workflow run.

        This method provides a complete audit view including:
        - Workflow run summary
        - All events with pagination
        - Stage-grouped events
        - Sequence validation results

        Args:
            workflow_run_id: Unique identifier for the workflow run
            offset: Event pagination offset (default: 0)
            limit: Event pagination limit (default: 100, max: 500)

        Returns:
            Dictionary containing audit data compatible with WorkflowRunAuditResponse:
            {
                "workflow_run": WorkflowRunSummary,
                "events": List[event_dict],
                "stages": List[stage_info_dict],
                "validation": validation_result_dict,
                "total_event_count": int,
                "offset": int,
                "limit": int,
                "has_next": bool
            }

        Raises:
            WorkflowRunNotFoundError: If workflow run doesn't exist
        """
        pass
