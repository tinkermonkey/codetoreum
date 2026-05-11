"""
Workflow Query Input Port

This module defines the input port interface for workflow query operations,
including retrieving, listing, and searching workflow definitions.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Any


class WorkflowSortField(Enum):
    """Fields available for sorting workflow lists"""

    NAME = "name"
    CREATED_AT = "created_at"
    UPDATED_AT = "updated_at"
    VERSION = "version"


class SortOrder(Enum):
    """Sort order"""

    ASC = "asc"
    DESC = "desc"


@dataclass
class WorkflowFilters:
    """Filters for listing workflows"""

    project_id: str | None = None
    is_template: bool | None = None
    is_active: bool | None = None
    work_item_type: str | None = None  # Filter by applicable work item types
    name_contains: str | None = None  # Partial name match


@dataclass
class WorkflowPaginationParams:
    """Pagination parameters for workflow queries"""

    offset: int = 0
    limit: int = 20
    sort_by: WorkflowSortField = WorkflowSortField.UPDATED_AT
    sort_order: SortOrder = SortOrder.DESC


@dataclass
class StageInfo:
    """Information about a workflow stage"""

    name: str
    agent_name: str
    timeout_seconds: int | None
    retry_count: int
    entry_conditions: list[dict[str, Any]]
    metadata: dict[str, Any]


@dataclass
class StageTransitionInfo:
    """Information about a stage transition"""

    from_stage: str
    to_stage: str
    condition: str | None


@dataclass
class WorkflowDefinitionInfo:
    """Complete workflow definition information"""

    id: str
    name: str
    description: str
    project_id: str
    version: int
    stages: list[StageInfo]
    transitions: list[StageTransitionInfo]
    work_item_types: list[str]
    is_template: bool
    is_active: bool
    created_at: datetime
    updated_at: datetime
    metadata: dict[str, Any]


@dataclass
class WorkflowSummaryInfo:
    """Summary information for workflow list"""

    id: str
    name: str
    description: str
    project_id: str
    version: int
    stage_count: int
    work_item_types: list[str]
    is_template: bool
    is_active: bool
    created_at: datetime
    updated_at: datetime


@dataclass
class WorkflowListResult:
    """Result of listing workflows"""

    workflows: list[WorkflowSummaryInfo]
    total_count: int
    offset: int
    limit: int
    has_next: bool


@dataclass
class WorkflowVersionInfo:
    """Information about a specific workflow version"""

    version: int
    created_at: datetime
    created_by: str | None
    changes_summary: str


@dataclass
class WorkflowVersionHistoryResult:
    """Result of querying workflow version history"""

    workflow_id: str
    versions: list[WorkflowVersionInfo]
    total_count: int


@dataclass
class WorkflowValidationError:
    """Workflow validation error"""

    error_type: str
    message: str
    stage_name: str | None
    details: dict[str, Any]


@dataclass
class WorkflowValidationResult:
    """Result of workflow validation"""

    is_valid: bool
    errors: list[WorkflowValidationError]
    warnings: list[str]


class IWorkflowQueryPort(ABC):
    """
    Input port for workflow queries.

    This port provides read-only access to workflow definitions, including
    retrieving individual workflows, listing with filters, version history, and validation.

    Implementations of this port should:
    - Query workflow storage for definitions
    - Transform data into appropriate response formats
    - Handle pagination for large result sets
    - Support filtering and sorting
    """

    @abstractmethod
    async def get_workflow(self, workflow_id: str, version: int | None = None) -> WorkflowDefinitionInfo:
        """
        Retrieves a workflow definition by ID.

        Args: workflow_id: Unique identifier for the workflow
            version: Optional specific version to retrieve (defaults to latest)

        Returns: Complete workflow definition

        Raises: WorkflowNotFoundError: If workflow doesn't exist
            VersionNotFoundError: If requested version doesn't exist
        """

    @abstractmethod
    async def list_workflows(
        self,
        filters: WorkflowFilters | None = None,
        pagination: WorkflowPaginationParams | None = None,
    ) -> WorkflowListResult:
        """
        Lists workflows matching the specified criteria.

        Args: filters: Optional filters to apply
            pagination: Pagination parameters

        Returns: Paginated list of workflow summaries

        Raises: ValidationError: If parameters are invalid
        """

    @abstractmethod
    async def get_workflow_versions(self, workflow_id: str, limit: int = 10) -> WorkflowVersionHistoryResult:
        """
        Retrieves version history for a workflow.

        Args: workflow_id: Unique identifier for the workflow
            limit: Maximum number of versions to return

        Returns: List of workflow versions with metadata

        Raises: WorkflowNotFoundError: If workflow doesn't exist
        """

    @abstractmethod
    async def validate_workflow(self, workflow_id: str, version: int | None = None) -> WorkflowValidationResult:
        """
        Validates a workflow definition.

        Checks for:
        - Circular stage dependencies
        - Invalid agent references
        - Entry condition validity
        - Transition consistency

        Args: workflow_id: Unique identifier for the workflow
            version: Optional specific version to validate (defaults to latest)

        Returns: Validation result with errors and warnings

        Raises: WorkflowNotFoundError: If workflow doesn't exist
        """

    @abstractmethod
    async def get_workflows_for_work_item_type(
        self, work_item_type: str, project_id: str | None = None
    ) -> list[WorkflowSummaryInfo]:
        """
        Retrieves workflows applicable to a specific work item type.

        Args: work_item_type: Type of work item (issue, pr, discussion, etc.)
            project_id: Optional project filter

        Returns: List of applicable workflow summaries

        Raises: ValidationError: If work item type is invalid
        """

    @abstractmethod
    async def count_active_executions(self, workflow_id: str) -> int:
        """
        Counts active executions for a workflow.

        Used to determine if a workflow can be safely deleted.

        Args: workflow_id: Unique identifier for the workflow

        Returns: Number of active (running or queued) executions

        Raises: WorkflowNotFoundError: If workflow doesn't exist
        """
