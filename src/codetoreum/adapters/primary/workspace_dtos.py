"""
Workspace DTOs

Data Transfer Objects for workspace status API endpoints.
"""

from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


# ============================================================================
# Response DTOs
# ============================================================================


class MountedFileInfo(BaseModel):
    """Mounted file information"""
    source_path: str
    container_path: str
    read_only: bool
    size_bytes: int


class ResourceUsageInfo(BaseModel):
    """Container resource usage"""
    cpu_percent: float
    memory_mb: float
    memory_limit_mb: Optional[float]
    memory_percent: Optional[float]
    disk_usage_mb: float
    disk_limit_mb: Optional[float]
    network_rx_bytes: int
    network_tx_bytes: int


class WorkspaceResponse(BaseModel):
    """Workspace information response"""
    workspace_id: str
    execution_id: str
    agent_id: str
    agent_name: str
    work_item_id: str
    project_id: str

    # Container details
    container_id: Optional[str]
    container_name: Optional[str]
    image_name: str
    status: str  # initializing, running, paused, stopped, failed, cleanup

    # Resource usage
    resource_usage: Optional[ResourceUsageInfo]

    # Mounted files and context
    mounted_files: List[MountedFileInfo]
    context_path: str
    artifacts_path: Optional[str]

    # Environment
    environment_variables: Dict[str, str]  # Without sensitive values
    working_directory: str

    # Timestamps
    created_at: datetime
    started_at: Optional[datetime]
    stopped_at: Optional[datetime]
    last_activity: Optional[datetime]

    # Metadata
    metadata: Dict[str, Any]


class WorkspaceListItemResponse(BaseModel):
    """Workspace list item (lightweight)"""
    workspace_id: str
    execution_id: str
    agent_name: str
    work_item_id: str
    status: str
    cpu_percent: Optional[float]
    memory_mb: Optional[float]
    created_at: datetime
    last_activity: Optional[datetime]


class WorkspaceListResponse(BaseModel):
    """List of workspaces response"""
    workspaces: List[WorkspaceListItemResponse]
    total_count: int
    active_count: int
    total_cpu_percent: float
    total_memory_mb: float


class ResourceUsageSummaryResponse(BaseModel):
    """Resource usage summary"""
    total_workspaces: int
    active_workspaces: int
    stopped_workspaces: int
    failed_workspaces: int
    total_cpu_percent: float
    total_memory_mb: float
    total_disk_mb: float
    avg_cpu_percent: float
    avg_memory_mb: float


class WorkspaceLogsResponse(BaseModel):
    """Workspace container logs"""
    workspace_id: str
    logs: List[str]
    total_lines: int
    truncated: bool
