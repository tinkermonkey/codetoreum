"""
Workspace REST API Router

Provides RESTful endpoints for workspace status, container monitoring,
and resource usage tracking.
"""

from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status

from codetoreum.adapters.primary.simple_auth_dependencies import SimpleAuthDependencies
from codetoreum.adapters.primary.workspace_dtos import (
    MountedFileInfo,
    ResourceUsageSummaryResponse,
    ResourceUsageInfo,
    WorkspaceListItemResponse,
    WorkspaceLogsResponse,
    WorkspaceListResponse,
    WorkspaceResponse,
)
from codetoreum.ports.input.workspace_query import (
    IWorkspaceQueryPort,
    PaginationParams,
    WorkspaceFilters,
    WorkspaceStatus,
)


def create_workspace_router(
    query_port: IWorkspaceQueryPort,
    auth_deps: Optional[SimpleAuthDependencies] = None,
) -> APIRouter:
    """
    Create the workspace REST API router.

    Args:
        query_port: Workspace query input port
        auth_deps: Optional authentication dependencies

    Returns:
        Configured APIRouter for workspace management
    """
    # Create router with authentication dependency if provided
    router_kwargs = {
        "prefix": "/api/v2/workspace",
        "tags": ["workspace"],
    }
    if auth_deps:
        router_kwargs["dependencies"] = [Depends(auth_deps.require_auth)]

    router = APIRouter(**router_kwargs)

    # ========================================================================
    # Workspace Status
    # ========================================================================

    @router.get(
        "/status",
        response_model=WorkspaceListResponse,
        summary="List all workspaces",
        response_description="List of workspaces with resource usage",
    )
    async def list_workspaces(
        execution_id: Optional[str] = Query(None, description="Filter by execution ID"),
        agent_id: Optional[str] = Query(None, description="Filter by agent ID"),
        work_item_id: Optional[str] = Query(None, description="Filter by work item ID"),
        project_id: Optional[str] = Query(None, description="Filter by project ID"),
        status: Optional[str] = Query(None, description="Filter by status (running, stopped, etc.)"),
        offset: int = Query(0, ge=0, description="Pagination offset"),
        limit: int = Query(50, ge=1, le=100, description="Pagination limit"),
    ) -> WorkspaceListResponse:
        """
        List all workspaces with optional filtering.

        Returns lightweight workspace information with resource usage
        for monitoring and dashboard purposes.

        **Query Parameters:**
        - execution_id: Filter by specific execution
        - agent_id: Filter by agent
        - work_item_id: Filter by work item
        - project_id: Filter by project
        - status: Filter by status (initializing, running, paused, stopped, failed, cleanup)
        - offset: Pagination offset (default: 0)
        - limit: Pagination limit (default: 50, max: 100)

        **Returns:**
        - 200 OK: List of workspaces
        - 400 Bad Request: Invalid filter parameters
        - 401 Unauthorized: Authentication required

        **Example Response:**
        ```json
        {
          "workspaces": [
            {
              "workspace_id": "ws-123",
              "execution_id": "exec-456",
              "agent_name": "software_engineer",
              "work_item_id": "wi-789",
              "status": "running",
              "cpu_percent": 25.5,
              "memory_mb": 512.0,
              "created_at": "2025-11-04T10:00:00Z",
              "last_activity": "2025-11-04T10:30:00Z"
            }
          ],
          "total_count": 1,
          "active_count": 1,
          "total_cpu_percent": 25.5,
          "total_memory_mb": 512.0
        }
        ```
        """
        try:
            # Parse filters
            filters = WorkspaceFilters(
                execution_id=execution_id,
                agent_id=agent_id,
                work_item_id=work_item_id,
                project_id=project_id,
                status=WorkspaceStatus(status) if status else None,
            )

            pagination = PaginationParams(offset=offset, limit=limit)

            # Get workspace list
            result = await query_port.list_workspaces(
                filters=filters,
                pagination=pagination,
            )

            return WorkspaceListResponse(
                workspaces=[
                    WorkspaceListItemResponse(
                        workspace_id=w.workspace_id,
                        execution_id=w.execution_id,
                        agent_name=w.agent_name,
                        work_item_id=w.work_item_id,
                        status=w.status.value,
                        cpu_percent=w.cpu_percent,
                        memory_mb=w.memory_mb,
                        created_at=w.created_at,
                        last_activity=w.last_activity,
                    )
                    for w in result.workspaces
                ],
                total_count=result.total_count,
                active_count=result.active_count,
                total_cpu_percent=result.total_cpu_percent,
                total_memory_mb=result.total_memory_mb,
            )

        except ValueError as e:
            # Invalid enum value
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid parameter: {str(e)}",
            )
        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to list workspaces: {str(e)}",
            )

    @router.get(
        "/active",
        response_model=WorkspaceListResponse,
        summary="List active workspaces",
        response_description="List of running and initializing workspaces",
    )
    async def list_active_workspaces(
        offset: int = Query(0, ge=0),
        limit: int = Query(50, ge=1, le=100),
    ) -> WorkspaceListResponse:
        """
        List all active workspaces (running or initializing).

        Convenience endpoint for monitoring currently executing agents.

        **Query Parameters:**
        - offset: Pagination offset
        - limit: Pagination limit

        **Returns:**
        - 200 OK: List of active workspaces
        - 401 Unauthorized: Authentication required
        """
        try:
            pagination = PaginationParams(offset=offset, limit=limit)

            result = await query_port.list_active_workspaces(pagination=pagination)

            return WorkspaceListResponse(
                workspaces=[
                    WorkspaceListItemResponse(
                        workspace_id=w.workspace_id,
                        execution_id=w.execution_id,
                        agent_name=w.agent_name,
                        work_item_id=w.work_item_id,
                        status=w.status.value,
                        cpu_percent=w.cpu_percent,
                        memory_mb=w.memory_mb,
                        created_at=w.created_at,
                        last_activity=w.last_activity,
                    )
                    for w in result.workspaces
                ],
                total_count=result.total_count,
                active_count=result.active_count,
                total_cpu_percent=result.total_cpu_percent,
                total_memory_mb=result.total_memory_mb,
            )

        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to list active workspaces: {str(e)}",
            )

    # ========================================================================
    # Workspace Details
    # ========================================================================

    @router.get(
        "/{workspace_id}",
        response_model=WorkspaceResponse,
        summary="Get workspace details",
        response_description="Detailed workspace information",
    )
    async def get_workspace(
        workspace_id: str,
    ) -> WorkspaceResponse:
        """
        Get detailed workspace information.

        Returns complete workspace details including mounted files,
        environment variables, resource usage, and timestamps.

        **Path Parameters:**
        - workspace_id: Workspace ID

        **Returns:**
        - 200 OK: Workspace details
        - 401 Unauthorized: Authentication required
        - 404 Not Found: Workspace not found

        **Example Response:**
        ```json
        {
          "workspace_id": "ws-123",
          "execution_id": "exec-456",
          "agent_id": "agent-789",
          "agent_name": "software_engineer",
          "work_item_id": "wi-101",
          "project_id": "proj-202",
          "container_id": "abc123def456",
          "container_name": "codetoreum-exec-456",
          "image_name": "codetoreum/agent:latest",
          "status": "running",
          "resource_usage": {
            "cpu_percent": 25.5,
            "memory_mb": 512.0,
            "memory_limit_mb": 2048.0,
            "memory_percent": 25.0,
            ...
          },
          "mounted_files": [
            {
              "source_path": "/workspace/src",
              "container_path": "/workspace/src",
              "read_only": false,
              "size_bytes": 1048576
            }
          ],
          ...
        }
        ```
        """
        try:
            workspace = await query_port.get_workspace(workspace_id=workspace_id)

            return WorkspaceResponse(
                workspace_id=workspace.workspace_id,
                execution_id=workspace.execution_id,
                agent_id=workspace.agent_id,
                agent_name=workspace.agent_name,
                work_item_id=workspace.work_item_id,
                project_id=workspace.project_id,
                container_id=workspace.container_id,
                container_name=workspace.container_name,
                image_name=workspace.image_name,
                status=workspace.status.value,
                resource_usage=ResourceUsageInfo(
                    cpu_percent=workspace.resource_usage.cpu_percent,
                    memory_mb=workspace.resource_usage.memory_mb,
                    memory_limit_mb=workspace.resource_usage.memory_limit_mb,
                    memory_percent=workspace.resource_usage.memory_percent,
                    disk_usage_mb=workspace.resource_usage.disk_usage_mb,
                    disk_limit_mb=workspace.resource_usage.disk_limit_mb,
                    network_rx_bytes=workspace.resource_usage.network_rx_bytes,
                    network_tx_bytes=workspace.resource_usage.network_tx_bytes,
                ) if workspace.resource_usage else None,
                mounted_files=[
                    MountedFileInfo(
                        source_path=f.source_path,
                        container_path=f.container_path,
                        read_only=f.read_only,
                        size_bytes=f.size_bytes,
                    )
                    for f in workspace.mounted_files
                ],
                context_path=workspace.context_path,
                artifacts_path=workspace.artifacts_path,
                environment_variables=workspace.environment_variables,
                working_directory=workspace.working_directory,
                created_at=workspace.created_at,
                started_at=workspace.started_at,
                stopped_at=workspace.stopped_at,
                last_activity=workspace.last_activity,
                metadata=workspace.metadata,
            )

        except Exception as e:
            # TODO(#XX): Use properly typed domain exceptions (WorkspaceNotFoundError, etc.)
            # instead of string matching. Requires domain exception classes to be implemented first.
            if "not found" in str(e).lower():
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"Workspace {workspace_id} not found",
                )
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to retrieve workspace: {str(e)}",
            )

    # ========================================================================
    # Resource Usage Summary
    # ========================================================================

    @router.get(
        "/resources/summary",
        response_model=ResourceUsageSummaryResponse,
        summary="Get resource usage summary",
        response_description="Aggregate resource usage across all workspaces",
    )
    async def get_resource_usage_summary(
        project_id: Optional[str] = Query(None, description="Filter by project"),
    ) -> ResourceUsageSummaryResponse:
        """
        Get aggregate resource usage across all workspaces.

        Returns total and average resource usage for monitoring
        and capacity planning.

        **Query Parameters:**
        - project_id: Optional filter by project

        **Returns:**
        - 200 OK: Resource usage summary
        - 401 Unauthorized: Authentication required

        **Example Response:**
        ```json
        {
          "total_workspaces": 10,
          "active_workspaces": 5,
          "stopped_workspaces": 3,
          "failed_workspaces": 2,
          "total_cpu_percent": 125.5,
          "total_memory_mb": 5120.0,
          "total_disk_mb": 10240.0,
          "avg_cpu_percent": 25.1,
          "avg_memory_mb": 1024.0
        }
        ```
        """
        try:
            summary = await query_port.get_resource_usage_summary(project_id=project_id)

            return ResourceUsageSummaryResponse(
                total_workspaces=summary.get("total_workspaces", 0),
                active_workspaces=summary.get("active_workspaces", 0),
                stopped_workspaces=summary.get("stopped_workspaces", 0),
                failed_workspaces=summary.get("failed_workspaces", 0),
                total_cpu_percent=summary.get("total_cpu_percent", 0.0),
                total_memory_mb=summary.get("total_memory_mb", 0.0),
                total_disk_mb=summary.get("total_disk_mb", 0.0),
                avg_cpu_percent=summary.get("avg_cpu_percent", 0.0),
                avg_memory_mb=summary.get("avg_memory_mb", 0.0),
            )

        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to retrieve resource usage summary: {str(e)}",
            )

    # ========================================================================
    # Workspace Logs
    # ========================================================================

    @router.get(
        "/{workspace_id}/logs",
        response_model=WorkspaceLogsResponse,
        summary="Get workspace container logs",
        response_description="Container logs",
    )
    async def get_workspace_logs(
        workspace_id: str,
        tail: Optional[int] = Query(None, ge=1, le=1000, description="Number of lines from end (max 1000)"),
        since: Optional[datetime] = Query(None, description="Filter logs from timestamp"),
    ) -> WorkspaceLogsResponse:
        """
        Get workspace container logs.

        Returns stdout/stderr logs from the agent container.

        **Path Parameters:**
        - workspace_id: Workspace ID

        **Query Parameters:**
        - tail: Number of lines from end (max 1000)
        - since: Filter logs from timestamp

        **Returns:**
        - 200 OK: Container logs
        - 401 Unauthorized: Authentication required
        - 404 Not Found: Workspace not found

        **Example Response:**
        ```json
        {
          "workspace_id": "ws-123",
          "logs": [
            "[2025-11-04 10:30:00] Starting agent execution...",
            "[2025-11-04 10:30:01] Loading context files...",
            "[2025-11-04 10:30:02] Running analysis..."
          ],
          "total_lines": 3,
          "truncated": false
        }
        ```
        """
        try:
            logs = await query_port.get_workspace_logs(
                workspace_id=workspace_id,
                tail=tail,
                since=since,
            )

            # Limit to 1000 lines for safety
            truncated = len(logs) > 1000
            if truncated:
                logs = logs[-1000:]

            return WorkspaceLogsResponse(
                workspace_id=workspace_id,
                logs=logs,
                total_lines=len(logs),
                truncated=truncated,
            )

        except Exception as e:
            # TODO(#XX): Use properly typed domain exceptions instead of string matching
            if "not found" in str(e).lower():
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"Workspace {workspace_id} not found",
                )
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to retrieve workspace logs: {str(e)}",
            )

    return router
