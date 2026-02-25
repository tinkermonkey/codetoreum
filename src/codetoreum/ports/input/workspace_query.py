"""
Workspace Query Input Port

This module defines the input port interface for querying workspace status,
including container information, mounted files, and resource usage.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Any


class WorkspaceStatus(str, Enum):
    """Workspace container status"""

    INITIALIZING = "initializing"
    RUNNING = "running"
    PAUSED = "paused"
    STOPPED = "stopped"
    FAILED = "failed"
    CLEANUP = "cleanup"


@dataclass
class MountedFile:
    """Information about a mounted file in the workspace"""

    source_path: str
    container_path: str
    read_only: bool
    size_bytes: int


@dataclass
class ResourceUsage:
    """Container resource usage"""

    cpu_percent: float
    memory_mb: float
    memory_limit_mb: float | None
    memory_percent: float | None
    disk_usage_mb: float
    disk_limit_mb: float | None
    network_rx_bytes: int
    network_tx_bytes: int


@dataclass
class WorkspaceInfo:
    """Workspace information"""

    workspace_id: str
    execution_id: str
    agent_id: str
    agent_name: str
    work_item_id: str
    project_id: str

    # Container details
    container_id: str | None
    container_name: str | None
    image_name: str
    status: WorkspaceStatus

    # Resource usage
    resource_usage: ResourceUsage | None

    # Mounted files and context
    mounted_files: list[MountedFile]
    context_path: str
    artifacts_path: str | None

    # Environment
    environment_variables: dict[str, str]  # Without sensitive values
    working_directory: str

    # Timestamps
    created_at: datetime
    started_at: datetime | None
    stopped_at: datetime | None
    last_activity: datetime | None

    # Metadata
    metadata: dict[str, Any]


@dataclass
class WorkspaceListItem:
    """Workspace list item (lightweight)"""

    workspace_id: str
    execution_id: str
    agent_name: str
    work_item_id: str
    status: WorkspaceStatus
    cpu_percent: float | None
    memory_mb: float | None
    created_at: datetime
    last_activity: datetime | None


@dataclass
class WorkspaceListResult:
    """List of workspaces"""

    workspaces: list[WorkspaceListItem]
    total_count: int
    active_count: int
    total_cpu_percent: float
    total_memory_mb: float


@dataclass
class WorkspaceFilters:
    """Filters for workspace queries"""

    execution_id: str | None = None
    agent_id: str | None = None
    work_item_id: str | None = None
    project_id: str | None = None
    status: WorkspaceStatus | None = None


@dataclass
class PaginationParams:
    """Pagination parameters"""

    offset: int = 0
    limit: int = 50


class IWorkspaceQueryPort(ABC):
    """
    Input port for workspace queries.

    This port provides read-only access to workspace information,
    including container status, mounted files, and resource usage.
    """

    @abstractmethod
    async def get_workspace(self, workspace_id: str) -> WorkspaceInfo:
        """
        Get workspace information by ID.

        Args:
            workspace_id: Workspace ID

        Returns:
            Workspace information

        Raises:
            WorkspaceNotFoundError: If workspace doesn't exist
        """

    @abstractmethod
    async def get_workspace_by_execution(self, execution_id: str) -> WorkspaceInfo:
        """
        Get workspace information by execution ID.

        Args:
            execution_id: Execution ID

        Returns:
            Workspace information

        Raises:
            WorkspaceNotFoundError: If workspace doesn't exist
        """

    @abstractmethod
    async def list_workspaces(
        self, filters: WorkspaceFilters | None = None, pagination: PaginationParams | None = None
    ) -> WorkspaceListResult:
        """
        List workspaces with optional filtering.

        Args:
            filters: Optional filters
            pagination: Optional pagination

        Returns:
            List of workspaces with aggregate stats
        """

    @abstractmethod
    async def list_active_workspaces(self, pagination: PaginationParams | None = None) -> WorkspaceListResult:
        """
        List all active workspaces (running or initializing).

        Args:
            pagination: Optional pagination

        Returns:
            List of active workspaces with resource usage
        """

    @abstractmethod
    async def get_resource_usage_summary(self, project_id: str | None = None) -> dict[str, Any]:
        """
        Get aggregate resource usage across workspaces.

        Args:
            project_id: Optional filter by project

        Returns:
            Dict with total CPU, memory, disk usage and container counts
        """

    @abstractmethod
    async def count_workspaces(self, filters: WorkspaceFilters | None = None) -> int:
        """
        Count workspaces matching filters.

        Args:
            filters: Optional filters

        Returns:
            Count of matching workspaces
        """

    @abstractmethod
    async def get_workspace_logs(
        self, workspace_id: str, tail: int | None = None, since: datetime | None = None
    ) -> list[str]:
        """
        Get workspace container logs.

        Args:
            workspace_id: Workspace ID
            tail: Optional number of lines from end
            since: Optional timestamp to filter from

        Returns:
            List of log lines

        Raises:
            WorkspaceNotFoundError: If workspace doesn't exist
        """
