"""
Mock Workspace Query Adapter

In-memory implementation of IWorkspaceQueryPort for development and testing.
"""

from datetime import datetime
from threading import RLock
from typing import Any

from codetoreum.domain.exceptions import WorkspaceNotFoundError
from codetoreum.ports.input.workspace_query import (
    IWorkspaceQueryPort,
    PaginationParams,
    ResourceUsage,
    WorkspaceFilters,
    WorkspaceInfo,
    WorkspaceListItem,
    WorkspaceListResult,
)


class MockWorkspaceQueryAdapter(IWorkspaceQueryPort):
    """
    Mock implementation of IWorkspaceQueryPort using in-memory storage.
    """

    def __init__(self):
        self._workspaces: dict[str, WorkspaceInfo] = {}
        self._workspaces_by_execution: dict[str, str] = {}  # execution_id -> workspace_id
        self._logs: dict[str, list[str]] = {}  # workspace_id -> log lines
        self._lock = RLock()

    def add_workspace(self, workspace_info: WorkspaceInfo):
        """Helper method to add a workspace to mock storage."""
        with self._lock:
            self._workspaces[workspace_info.workspace_id] = workspace_info
            self._workspaces_by_execution[workspace_info.execution_id] = workspace_info.workspace_id
            if workspace_info.workspace_id not in self._logs:
                self._logs[workspace_info.workspace_id] = []

    def update_resource_usage(self, workspace_id: str, usage: ResourceUsage):
        """Helper method to update resource usage (for testing)."""
        with self._lock:
            if workspace_id in self._workspaces:
                self._workspaces[workspace_id].resource_usage = usage

    def add_log_line(self, workspace_id: str, log_line: str):
        """Helper method to add a log line (for testing)."""
        with self._lock:
            if workspace_id not in self._logs:
                self._logs[workspace_id] = []
            self._logs[workspace_id].append(log_line)

    async def get_workspace(self, workspace_id: str) -> WorkspaceInfo:
        """Get workspace information by ID."""
        with self._lock:
            if workspace_id not in self._workspaces:
                msg = f"Workspace with ID {workspace_id} not found"
                raise WorkspaceNotFoundError(msg)
            return self._workspaces[workspace_id]

    async def get_workspace_by_execution(self, execution_id: str) -> WorkspaceInfo:
        """Get workspace information by execution ID."""
        with self._lock:
            if execution_id not in self._workspaces_by_execution:
                msg = f"Workspace for execution {execution_id} not found"
                raise WorkspaceNotFoundError(msg)
            workspace_id = self._workspaces_by_execution[execution_id]
            return self._workspaces[workspace_id]

    async def list_workspaces(
        self,
        filters: WorkspaceFilters | None = None,
        pagination: PaginationParams | None = None,
    ) -> WorkspaceListResult:
        """List workspaces with optional filtering."""
        with self._lock:
            # Get all workspaces
            workspaces = list(self._workspaces.values())

            # Apply filters
            if filters:
                workspaces = self._apply_filters(workspaces, filters)

            # Convert to list items
            list_items = [self._to_list_item(ws) for ws in workspaces]

            total_count = len(list_items)

            # Apply pagination
            offset = 0
            limit = 50
            if pagination:
                offset = pagination.offset
                limit = pagination.limit

            paginated_items = list_items[offset : offset + limit]

            # Calculate aggregate stats
            active_count = sum(1 for ws in workspaces if ws.status.value in ["initializing", "running"])
            total_cpu = sum(ws.resource_usage.cpu_percent if ws.resource_usage else 0.0 for ws in workspaces)
            total_memory = sum(ws.resource_usage.memory_mb if ws.resource_usage else 0.0 for ws in workspaces)

            return WorkspaceListResult(
                workspaces=paginated_items,
                total_count=total_count,
                active_count=active_count,
                total_cpu_percent=total_cpu,
                total_memory_mb=total_memory,
            )

    async def list_active_workspaces(self, pagination: PaginationParams | None = None) -> WorkspaceListResult:
        """List all active workspaces (running or initializing)."""
        # Filter for active statuses in the list method
        with self._lock:
            workspaces = [ws for ws in self._workspaces.values() if ws.status.value in ["initializing", "running"]]

            list_items = [self._to_list_item(ws) for ws in workspaces]

            total_count = len(list_items)

            # Apply pagination
            offset = 0
            limit = 50
            if pagination:
                offset = pagination.offset
                limit = pagination.limit

            paginated_items = list_items[offset : offset + limit]

            # Calculate aggregate stats
            active_count = len(workspaces)
            total_cpu = sum(ws.resource_usage.cpu_percent if ws.resource_usage else 0.0 for ws in workspaces)
            total_memory = sum(ws.resource_usage.memory_mb if ws.resource_usage else 0.0 for ws in workspaces)

            return WorkspaceListResult(
                workspaces=paginated_items,
                total_count=total_count,
                active_count=active_count,
                total_cpu_percent=total_cpu,
                total_memory_mb=total_memory,
            )

    async def get_resource_usage_summary(self, project_id: str | None = None) -> dict[str, Any]:
        """Get aggregate resource usage across workspaces."""
        with self._lock:
            workspaces = list(self._workspaces.values())

            if project_id:
                workspaces = [ws for ws in workspaces if ws.project_id == project_id]

            total_containers = len(workspaces)
            active_containers = sum(1 for ws in workspaces if ws.status.value in ["initializing", "running"])
            total_cpu = sum(ws.resource_usage.cpu_percent if ws.resource_usage else 0.0 for ws in workspaces)
            total_memory = sum(ws.resource_usage.memory_mb if ws.resource_usage else 0.0 for ws in workspaces)
            total_disk = sum(ws.resource_usage.disk_usage_mb if ws.resource_usage else 0.0 for ws in workspaces)

            return {
                "total_containers": total_containers,
                "active_containers": active_containers,
                "total_cpu_percent": total_cpu,
                "total_memory_mb": total_memory,
                "total_disk_mb": total_disk,
            }

    async def count_workspaces(self, filters: WorkspaceFilters | None = None) -> int:
        """Count workspaces matching filters."""
        with self._lock:
            workspaces = list(self._workspaces.values())

            if filters:
                workspaces = self._apply_filters(workspaces, filters)

            return len(workspaces)

    async def get_workspace_logs(
        self,
        workspace_id: str,
        tail: int | None = None,
        since: datetime | None = None,
    ) -> list[str]:
        """Get workspace container logs."""
        with self._lock:
            if workspace_id not in self._workspaces:
                msg = f"Workspace with ID {workspace_id} not found"
                raise WorkspaceNotFoundError(msg)

            logs = self._logs.get(workspace_id, [])

            # Apply tail if specified
            if tail:
                logs = logs[-tail:]

            # Note: since filtering would require timestamp parsing in real implementation
            # For mock, we ignore it

            return logs

    def _apply_filters(self, workspaces: list[WorkspaceInfo], filters: WorkspaceFilters) -> list[WorkspaceInfo]:
        """Apply filters to workspace list."""
        result = workspaces

        if filters.execution_id is not None:
            result = [ws for ws in result if ws.execution_id == filters.execution_id]

        if filters.agent_id is not None:
            result = [ws for ws in result if ws.agent_id == filters.agent_id]

        if filters.work_item_id is not None:
            result = [ws for ws in result if ws.work_item_id == filters.work_item_id]

        if filters.project_id is not None:
            result = [ws for ws in result if ws.project_id == filters.project_id]

        if filters.status is not None:
            result = [ws for ws in result if ws.status == filters.status]

        return result

    def _to_list_item(self, workspace: WorkspaceInfo) -> WorkspaceListItem:
        """Convert WorkspaceInfo to WorkspaceListItem."""
        return WorkspaceListItem(
            workspace_id=workspace.workspace_id,
            execution_id=workspace.execution_id,
            agent_name=workspace.agent_name,
            work_item_id=workspace.work_item_id,
            status=workspace.status,
            cpu_percent=(workspace.resource_usage.cpu_percent if workspace.resource_usage else None),
            memory_mb=(workspace.resource_usage.memory_mb if workspace.resource_usage else None),
            created_at=workspace.created_at,
            last_activity=workspace.last_activity,
        )

    def clear(self):
        """Clear all data (useful for testing)."""
        with self._lock:
            self._workspaces.clear()
            self._workspaces_by_execution.clear()
            self._logs.clear()
