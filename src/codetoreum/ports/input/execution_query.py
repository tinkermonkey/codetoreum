"""
Execution Query Port Interface

Defines the contract for querying agent execution information.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from enum import Enum

from codetoreum.domain.agent_execution import ExecutionStatus

# ============================================================================
# Filters and Pagination
# ============================================================================


@dataclass
class ExecutionFilters:
    """Filters for execution queries."""

    status: ExecutionStatus | None = None
    agent_id: str | None = None
    work_item_id: str | None = None
    workflow_id: str | None = None
    stage_name: str | None = None
    start_date: datetime | None = None
    end_date: datetime | None = None


class ExecutionSortField(Enum):
    """Fields available for sorting executions."""

    INITIALIZED_AT = "initialized_at"
    STARTED_AT = "started_at"
    COMPLETED_AT = "completed_at"
    DURATION = "duration_seconds"
    STATUS = "status"


class SortOrder(Enum):
    """Sort order enumeration."""

    ASC = "asc"
    DESC = "desc"


@dataclass
class ExecutionPaginationParams:
    """Pagination parameters for execution list."""

    offset: int = 0
    limit: int = 20
    sort_by: ExecutionSortField = ExecutionSortField.INITIALIZED_AT
    sort_order: SortOrder = SortOrder.DESC


# ============================================================================
# Result Models
# ============================================================================


class ErrorType(Enum):
    """Types of execution errors."""

    CONTAINER_CRASHED = "CONTAINER_CRASHED"
    EXECUTION_TIMEOUT = "EXECUTION_TIMEOUT"
    AGENT_FAILURE = "AGENT_FAILURE"
    UNKNOWN = "UNKNOWN"


@dataclass
class ContainerStatus:
    """Container status information."""

    container_id: str | None
    container_name: str | None
    last_known_status: str | None
    exit_code: int | None


@dataclass
class ExecutionErrorDetail:
    """Detailed error information."""

    error_type: ErrorType
    message: str
    container_status: ContainerStatus | None = None
    partial_logs_available: bool = False


@dataclass
class ExecutionInfo:
    """Execution information for query results."""

    # Identity
    id: str
    agent_id: str
    agent_name: str
    work_item_id: str
    workflow_id: str
    stage_name: str

    # Status
    status: ExecutionStatus

    # Container info
    container_name: str | None
    container_id: str | None

    # Results
    output: str | None
    error_message: str | None
    error_detail: ExecutionErrorDetail | None
    exit_code: int | None

    # Metrics
    input_tokens: int
    output_tokens: int
    duration_seconds: float | None

    # Timestamps
    initialized_at: datetime
    started_at: datetime | None
    completed_at: datetime | None

    # Calculated fields
    elapsed_time_seconds: float | None = None
    current_stage: str | None = None


@dataclass
class LogEntry:
    """Single log entry."""

    timestamp: datetime
    level: str
    message: str
    stage: str | None = None


@dataclass
class ExecutionLogs:
    """Execution logs with metadata."""

    execution_id: str
    logs: list[LogEntry]
    total_lines: int
    stage: str | None = None
    has_more: bool = False


@dataclass
class ExecutionListResult:
    """Result for execution list queries."""

    executions: list[ExecutionInfo]
    total_count: int
    offset: int
    limit: int
    has_next: bool


@dataclass
class ExecutionHistoryEntry:
    """Single entry in execution history (event)."""

    event_type: str
    occurred_at: datetime
    payload: dict


@dataclass
class ExecutionHistory:
    """Execution event history."""

    execution_id: str
    events: list[ExecutionHistoryEntry]
    total_events: int


# ============================================================================
# Port Interface
# ============================================================================


class IExecutionQueryPort(ABC):
    """
    Execution Query Input Port.

    Provides read-only access to execution information including status,
    logs, and history.
    """

    @abstractmethod
    async def get_execution(self, execution_id: str) -> ExecutionInfo:
        """
        Get execution by ID.

        Args:
            execution_id: Execution ID

        Returns:
            ExecutionInfo with execution details including error details

        Raises:
            ExecutionNotFoundError: If execution doesn't exist
        """

    @abstractmethod
    async def list_executions(
        self,
        filters: ExecutionFilters | None = None,
        pagination: ExecutionPaginationParams | None = None,
    ) -> ExecutionListResult:
        """
        List executions with optional filtering and pagination.

        Args:
            filters: Optional filters for execution selection
            pagination: Optional pagination parameters

        Returns:
            ExecutionListResult with matching executions
        """

    @abstractmethod
    async def get_execution_logs(
        self,
        execution_id: str,
        stage: str | None = None,
        tail: int | None = None,
    ) -> ExecutionLogs:
        """
        Get execution logs.

        Args:
            execution_id: Execution ID
            stage: Optional filter by stage name
            tail: Optional limit to last N lines

        Returns:
            ExecutionLogs with log entries

        Raises:
            ExecutionNotFoundError: If execution doesn't exist
        """

    @abstractmethod
    async def get_execution_history(
        self, execution_id: str, limit: int | None = None
    ) -> ExecutionHistory:
        """
        Get execution event history.

        Args:
            execution_id: Execution ID
            limit: Optional limit on number of events

        Returns:
            ExecutionHistory with timeline of events

        Raises:
            ExecutionNotFoundError: If execution doesn't exist
        """

    @abstractmethod
    async def count_executions(self, filters: ExecutionFilters | None = None) -> int:
        """
        Count executions matching filters.

        Args:
            filters: Optional filters for execution selection

        Returns:
            Count of matching executions
        """
