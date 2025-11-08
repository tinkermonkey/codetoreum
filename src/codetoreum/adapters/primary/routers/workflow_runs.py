"""
Workflow Runs REST API Router

Provides RESTful endpoints for querying workflow execution runs.
"""

from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi import status as http_status

from codetoreum.adapters.primary.simple_auth_dependencies import SimpleAuthDependencies
from codetoreum.adapters.primary.workflow_run_dtos import (
    WorkflowRunResponse,
    WorkflowRunListResponse,
    WorkflowEventsListResponse,
)
from codetoreum.adapters.primary.workflow_run_mappers import WorkflowRunMapper
from codetoreum.ports.input.workflow_run_query import (
    IWorkflowRunQueryPort,
    WorkflowRunFilters,
    WorkflowRunPaginationParams,
    WorkflowRunSortField,
    WorkflowRunStatus,
    SortOrder,
)
from codetoreum.config import (
    DEFAULT_PAGE_SIZE,
    MAX_PAGE_SIZE,
    DEFAULT_OFFSET,
)


def create_workflow_runs_router(
    query_port: IWorkflowRunQueryPort,
    auth_deps: Optional[SimpleAuthDependencies] = None,
) -> APIRouter:
    """
    Create the workflow runs REST API router.

    Args:
        query_port: Workflow run query input port
        auth_deps: Optional authentication dependencies

    Returns:
        Configured APIRouter for workflow runs
    """
    # Create router with authentication dependency if provided
    router_kwargs = {
        "prefix": "/api/v2/workflows/runs",
        "tags": ["workflow-runs"],
    }
    if auth_deps:
        router_kwargs["dependencies"] = [Depends(auth_deps.require_auth)]

    router = APIRouter(**router_kwargs)

    # ========================================================================
    # List Workflow Runs
    # ========================================================================

    @router.get(
        "",
        response_model=WorkflowRunListResponse,
        summary="List workflow runs with filtering and pagination",
        response_description="List of workflow runs",
    )
    async def list_workflow_runs(
        status: Optional[str] = Query(None, description="Filter by status (comma-separated: running,completed,failed,cancelled)"),
        projectId: Optional[str] = Query(None, description="Filter by project ID", alias="projectId"),
        workItemId: Optional[str] = Query(None, description="Filter by work item ID", alias="workItemId"),
        workflowId: Optional[str] = Query(None, description="Filter by workflow template ID", alias="workflowId"),
        offset: int = Query(DEFAULT_OFFSET, ge=0, description="Offset for pagination"),
        limit: int = Query(DEFAULT_PAGE_SIZE, ge=1, le=MAX_PAGE_SIZE, description=f"Limit for pagination (max {MAX_PAGE_SIZE})"),
        sortBy: str = Query("startedAt", description="Sort field (startedAt, completedAt, duration)", alias="sortBy"),
        sortOrder: str = Query("desc", description="Sort order (asc, desc)", alias="sortOrder"),
    ) -> WorkflowRunListResponse:
        """
        List workflow runs with optional filtering and pagination.

        **Query Parameters:**
        - status: Filter by status (comma-separated)
        - projectId: Filter by project ID
        - workItemId: Filter by work item ID
        - workflowId: Filter by workflow template ID
        - offset: Pagination offset (default: 0)
        - limit: Pagination limit (default: 20, max: 100)
        - sortBy: Sort field (startedAt, completedAt, duration)
        - sortOrder: Sort order (asc, desc)

        **Returns:**
        - 200 OK: List of workflow runs with pagination metadata
        - 400 Bad Request: Invalid filter parameters
        - 401 Unauthorized: Authentication required

        **Examples:**
        - List all runs: `GET /api/v2/workflows/runs`
        - Filter by status: `GET /api/v2/workflows/runs?status=running,completed`
        - Filter by project: `GET /api/v2/workflows/runs?projectId=proj-123`
        """
        try:
            # Parse status filter
            status_list = None
            if status:
                try:
                    status_list = [WorkflowRunStatus(s.strip()) for s in status.split(",")]
                except ValueError as e:
                    raise HTTPException(
                        status_code=http_status.HTTP_400_BAD_REQUEST,
                        detail=f"Invalid status value: {str(e)}",
                    )

            # Parse filters
            filters = WorkflowRunFilters(
                status=status_list,
                project_id=projectId,
                work_item_id=workItemId,
                workflow_id=workflowId,
            )

            # Parse sort field
            try:
                sort_field = WorkflowRunSortField(sortBy)
            except ValueError:
                raise HTTPException(
                    status_code=http_status.HTTP_400_BAD_REQUEST,
                    detail=f"Invalid sort field: {sortBy}. Must be one of: startedAt, completedAt, duration",
                )

            # Parse sort order
            try:
                sort_order_enum = SortOrder(sortOrder.lower())
            except ValueError:
                raise HTTPException(
                    status_code=http_status.HTTP_400_BAD_REQUEST,
                    detail=f"Invalid sort order: {sortOrder}. Must be 'asc' or 'desc'",
                )

            # Parse pagination
            pagination = WorkflowRunPaginationParams(
                offset=offset,
                limit=limit,
                sort_by=sort_field,
                sort_order=sort_order_enum,
            )

            # Execute query via port
            result = await query_port.list_workflow_runs(filters, pagination)

            # Convert to response DTO
            return WorkflowRunMapper.to_list_response(result)

        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(
                status_code=http_status.HTTP_400_BAD_REQUEST,
                detail=str(e),
            )

    # ========================================================================
    # Get Workflow Run
    # ========================================================================

    @router.get(
        "/{workflow_run_id}",
        response_model=WorkflowRunResponse,
        summary="Get workflow run details",
        response_description="Workflow run including all stages",
    )
    async def get_workflow_run(
        workflow_run_id: str,
    ) -> WorkflowRunResponse:
        """
        Get detailed information about a specific workflow run.

        **Parameters:**
        - workflow_run_id: Workflow run ID

        **Returns:**
        - 200 OK: Workflow run with all stages
        - 401 Unauthorized: Authentication required
        - 404 Not Found: Workflow run not found

        **Response includes:**
        - All workflow run metadata
        - Complete stage information with execution IDs
        - Current status and progress
        """
        try:
            # Get workflow run
            run_info = await query_port.get_workflow_run(workflow_run_id)

            # Convert to response DTO
            return WorkflowRunMapper.to_response(run_info)

        except Exception as e:
            error_msg = str(e).lower()
            if "not found" in error_msg:
                raise HTTPException(
                    status_code=http_status.HTTP_404_NOT_FOUND,
                    detail=f"Workflow run not found: {workflow_run_id}",
                )
            raise HTTPException(
                status_code=http_status.HTTP_400_BAD_REQUEST,
                detail=str(e),
            )

    # ========================================================================
    # Get Workflow Run Events
    # ========================================================================

    @router.get(
        "/{workflow_run_id}/events",
        response_model=WorkflowEventsListResponse,
        summary="Get workflow run events",
        response_description="List of events for this workflow run",
    )
    async def get_workflow_run_events(
        workflow_run_id: str,
        offset: int = Query(0, ge=0, description="Pagination offset"),
        limit: int = Query(50, ge=1, le=200, description="Pagination limit (default 50, max 200)"),
        eventTypes: Optional[str] = Query(None, description="Filter by event types (comma-separated)", alias="eventTypes"),
        since: Optional[datetime] = Query(None, description="ISO timestamp - events after this time"),
    ) -> WorkflowEventsListResponse:
        """
        Get events for a specific workflow run.

        **Parameters:**
        - workflow_run_id: Workflow run ID

        **Query Parameters:**
        - offset: Pagination offset (default: 0)
        - limit: Pagination limit (default: 50, max: 200)
        - eventTypes: Filter by event types (comma-separated)
        - since: ISO timestamp - events after this time

        **Returns:**
        - 200 OK: List of events with pagination metadata
        - 401 Unauthorized: Authentication required
        - 404 Not Found: Workflow run not found

        **Response includes:**
        - Event ID, type, and timestamp
        - Agent and stage information (if applicable)
        - Event-specific data
        """
        try:
            # Parse event types filter
            event_type_list = None
            if eventTypes:
                event_type_list = [et.strip() for et in eventTypes.split(",")]

            # Get events via port
            result = await query_port.get_workflow_run_events(
                workflow_run_id=workflow_run_id,
                offset=offset,
                limit=limit,
                event_types=event_type_list,
                since=since,
            )

            # Convert to response DTO
            return WorkflowRunMapper.to_events_list_response(
                events=result.get("events", []),
                total_count=result.get("total_count", 0),
                offset=result.get("offset", offset),
                limit=result.get("limit", limit),
                has_next=result.get("has_next", False),
            )

        except Exception as e:
            error_msg = str(e).lower()
            if "not found" in error_msg:
                raise HTTPException(
                    status_code=http_status.HTTP_404_NOT_FOUND,
                    detail=f"Workflow run not found: {workflow_run_id}",
                )
            raise HTTPException(
                status_code=http_status.HTTP_400_BAD_REQUEST,
                detail=str(e),
            )

    return router
