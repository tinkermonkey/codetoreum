"""
Workflow Run Query Input Port

This module defines the input port interface for workflow run query operations,
including retrieving workflow execution runs, their status, and events.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from types import MappingProxyType
from typing import List, Optional, Mapping, Tuple


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


@dataclass(frozen=True)
class WorkflowRunFilters:
    """Filters for listing workflow runs"""
    status: Optional[Tuple[WorkflowRunStatus, ...]] = None  # Filter by status (comma-separated)
    project_id: Optional[str] = None  # Filter by project
    work_item_id: Optional[str] = None  # Filter by work item
    workflow_id: Optional[str] = None  # Filter by workflow template

    def __post_init__(self) -> None:
        """Validate filter fields."""
        # Validate non-empty string IDs
        if self.project_id is not None and not self.project_id.strip():
            raise ValueError("project_id must be non-empty if provided")
        if self.work_item_id is not None and not self.work_item_id.strip():
            raise ValueError("work_item_id must be non-empty if provided")
        if self.workflow_id is not None and not self.workflow_id.strip():
            raise ValueError("workflow_id must be non-empty if provided")
        # Validate non-empty status tuple
        if self.status is not None and len(self.status) == 0:
            raise ValueError("status must be non-empty if provided")


@dataclass
class WorkflowRunPaginationParams:
    """Pagination parameters for workflow run queries"""
    offset: int = 0
    limit: int = 20
    sort_by: WorkflowRunSortField = WorkflowRunSortField.STARTED_AT
    sort_order: SortOrder = SortOrder.DESC

    def __post_init__(self) -> None:
        """Validate pagination parameters."""
        if self.offset < 0:
            raise ValueError(f"offset must be >= 0, got {self.offset}")
        if self.limit <= 0:
            raise ValueError(f"limit must be > 0, got {self.limit}")
        if self.limit > 1000:
            raise ValueError(f"limit must be <= 1000 to prevent excessive memory usage, got {self.limit}")


@dataclass(frozen=True)
class WorkflowRunStageInfo:
    """Information about a workflow run stage"""
    name: str
    agent_name: str
    status: str  # pending, running, completed, failed
    started_at: Optional[datetime]
    completed_at: Optional[datetime]
    execution_id: Optional[str]
    output: Optional[str] = None
    error_message: Optional[str] = None
    metadata: Optional[Mapping] = None

    def __post_init__(self) -> None:
        """Initialize metadata and validate fields."""
        # Validate name is non-empty
        if not self.name or not self.name.strip():
            raise ValueError("name must be a non-empty string")

        # Validate temporal consistency
        if self.started_at is not None and self.completed_at is not None:
            if self.completed_at < self.started_at:
                raise ValueError(
                    f"completedAt ({self.completed_at}) must be >= startedAt ({self.started_at})"
                )

        # Initialize metadata to empty immutable mapping if None
        if self.metadata is None:
            # Use object.__setattr__ since this is a frozen dataclass
            # Use MappingProxyType for true immutability
            object.__setattr__(self, 'metadata', MappingProxyType({}))


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


@dataclass
class WorkflowRunEventsResult:
    """Result of querying workflow run events"""
    events: List[dict]  # List of event dictionaries
    total_count: int
    offset: int
    limit: int
    has_next: bool

    def __post_init__(self) -> None:
        """Validate pagination parameters."""
        if self.offset < 0:
            raise ValueError(f"offset must be non-negative, got {self.offset}")
        if self.limit < 0:
            raise ValueError(f"limit must be non-negative, got {self.limit}")
        if self.total_count < 0:
            raise ValueError(f"total_count must be non-negative, got {self.total_count}")


@dataclass
class WorkflowRunAuditResult:
    """Result of querying workflow run audit information"""
    workflow_run: WorkflowRunSummary
    events: List[dict]  # List of event dictionaries
    stages: List[dict]  # List of stage information dictionaries
    validation: Optional[dict]  # Validation result dictionary (None if not requested)
    total_count: int
    offset: int
    limit: int
    has_next: bool

    def __post_init__(self) -> None:
        """Validate pagination parameters."""
        if self.offset < 0:
            raise ValueError(f"offset must be non-negative, got {self.offset}")
        if self.limit < 0:
            raise ValueError(f"limit must be non-negative, got {self.limit}")
        if self.total_count < 0:
            raise ValueError(f"total_count must be non-negative, got {self.total_count}")


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
    ) -> WorkflowRunEventsResult:
        """
        Retrieves events for a specific workflow run.

        Args:
            workflow_run_id: Unique identifier for the workflow run
            offset: Pagination offset
            limit: Pagination limit (default 50, max 200)
            event_types: Optional filter by event types (comma-separated)
            since: Optional ISO timestamp - events after this time

        Returns:
            WorkflowRunEventsResult containing events list and pagination info

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
        include_validation: bool = True,
    ) -> WorkflowRunAuditResult:
        """
        Retrieves comprehensive audit information for a workflow run.

        This method provides a complete audit view including:
        - Workflow run summary
        - All events with pagination
        - Stage-grouped events
        - Sequence validation results (optional)

        Args:
            workflow_run_id: Unique identifier for the workflow run
            offset: Event pagination offset (default: 0)
            limit: Event pagination limit (default: 100, max: 200)
            include_validation: Whether to validate event sequence (default: True)

        Returns:
            WorkflowRunAuditResult containing:
            - workflow_run: WorkflowRunSummary
            - events: List of event dictionaries
            - stages: List of stage info dictionaries
            - validation: Validation result dictionary or None
            - total_count: Total number of events
            - offset: Pagination offset
            - limit: Pagination limit
            - has_next: Whether more events are available

        Raises:
            WorkflowRunNotFoundError: If workflow run doesn't exist
        """
        pass
