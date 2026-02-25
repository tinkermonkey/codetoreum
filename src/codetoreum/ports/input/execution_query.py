"""
Execution Query Port Interface

Defines the contract for querying agent execution information.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import List, Optional

from codetoreum.domain.agent_execution import ExecutionStatus

# ============================================================================
# Filters and Pagination
# ============================================================================


@dataclass
class ExecutionFilters:
    """Filters for execution queries."""

    status: Optional[ExecutionStatus] = None
    agent_id: Optional[str] = None
    work_item_id: Optional[str] = None
    workflow_id: Optional[str] = None
    stage_name: Optional[str] = None
    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None


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

    container_id: Optional[str]
    container_name: Optional[str]
    last_known_status: Optional[str]
    exit_code: Optional[int]


@dataclass
class ExecutionErrorDetail:
    """Detailed error information."""

    error_type: ErrorType
    message: str
    container_status: Optional[ContainerStatus] = None
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
    container_name: Optional[str]
    container_id: Optional[str]

    # Results
    output: Optional[str]
    error_message: Optional[str]
    error_detail: Optional[ExecutionErrorDetail]
    exit_code: Optional[int]

    # Metrics
    input_tokens: int
    output_tokens: int
    duration_seconds: Optional[float]

    # Timestamps
    initialized_at: datetime
    started_at: Optional[datetime]
    completed_at: Optional[datetime]

    # Calculated fields
    elapsed_time_seconds: Optional[float] = None
    current_stage: Optional[str] = None


@dataclass
class LogEntry:
    """Single log entry."""

    timestamp: datetime
    level: str
    message: str
    stage: Optional[str] = None


@dataclass
class ExecutionLogs:
    """Execution logs with metadata."""

    execution_id: str
    logs: List[LogEntry]
    total_lines: int
    stage: Optional[str] = None
    has_more: bool = False


@dataclass
class ExecutionListResult:
    """Result for execution list queries."""

    executions: List[ExecutionInfo]
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
    events: List[ExecutionHistoryEntry]
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
        pass

    @abstractmethod
    async def list_executions(
        self,
        filters: Optional[ExecutionFilters] = None,
        pagination: Optional[ExecutionPaginationParams] = None,
    ) -> ExecutionListResult:
        """
        List executions with optional filtering and pagination.

        Args:
            filters: Optional filters for execution selection
            pagination: Optional pagination parameters

        Returns:
            ExecutionListResult with matching executions
        """
        pass

    @abstractmethod
    async def get_execution_logs(
        self,
        execution_id: str,
        stage: Optional[str] = None,
        tail: Optional[int] = None,
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
        pass

    @abstractmethod
    async def get_execution_history(
        self, execution_id: str, limit: Optional[int] = None
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
        pass

    @abstractmethod
    async def count_executions(self, filters: Optional[ExecutionFilters] = None) -> int:
        """
        Count executions matching filters.

        Args:
            filters: Optional filters for execution selection

        Returns:
            Count of matching executions
        """
        pass
