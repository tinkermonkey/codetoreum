"""
Workflow Runs REST API Router

Provides RESTful endpoints for querying workflow execution runs.
"""

import logging
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi import status as http_status

from codetoreum.adapters.primary.audit_dtos import WorkflowRunAuditResponse
from codetoreum.adapters.primary.simple_auth_dependencies import SimpleAuthDependencies
from codetoreum.adapters.primary.workflow_run_dtos import (
    WorkflowEventsListResponse,
    WorkflowRunListResponse,
    WorkflowRunResponse,
)
from codetoreum.adapters.primary.workflow_run_mappers import WorkflowRunMapper
from codetoreum.config import (
    DEFAULT_OFFSET,
    DEFAULT_PAGE_SIZE,
    MAX_PAGE_SIZE,
)
from codetoreum.config.defaults import AUDIT_EVENTS_MAX_PAGE_SIZE
from codetoreum.ports.exceptions import ResourceNotFoundError
from codetoreum.ports.input.workflow_run_query import (
    IWorkflowRunQueryPort,
    SortOrder,
    WorkflowRunFilters,
    WorkflowRunPaginationParams,
    WorkflowRunSortField,
    WorkflowRunStatus,
)

logger = logging.getLogger(__name__)


def create_workflow_runs_router(
    query_port: IWorkflowRunQueryPort,
    auth_deps: SimpleAuthDependencies | None = None,
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
        status: str | None = Query(
            None,
            description="Filter by status (comma-separated: running,completed,failed,cancelled)",
        ),
        projectId: str | None = Query(None, description="Filter by project ID", alias="projectId"),
        workItemId: str | None = Query(None, description="Filter by work item ID", alias="workItemId"),
        workflowId: str | None = Query(None, description="Filter by workflow template ID", alias="workflowId"),
        offset: int = Query(DEFAULT_OFFSET, ge=0, description="Offset for pagination"),
        limit: int = Query(
            DEFAULT_PAGE_SIZE,
            ge=1,
            le=MAX_PAGE_SIZE,
            description=f"Limit for pagination (max {MAX_PAGE_SIZE})",
        ),
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
                    status_list = tuple(WorkflowRunStatus(s.strip()) for s in status.split(","))
                except ValueError as e:
                    raise HTTPException(
                        status_code=http_status.HTTP_400_BAD_REQUEST,
                        detail=f"Invalid status value: {e!s}",
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
            logger.error(
                "Unexpected error listing workflow runs",
                exc_info=True,
                extra={"error": str(e)},
            )
            raise HTTPException(
                status_code=http_status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Internal server error while listing workflow runs",
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

        except ResourceNotFoundError as e:
            raise HTTPException(
                status_code=http_status.HTTP_404_NOT_FOUND,
                detail=str(e),
            )
        except HTTPException:
            raise
        except Exception as e:
            logger.error(
                "Unexpected error retrieving workflow run",
                exc_info=True,
                extra={"workflow_run_id": workflow_run_id, "error": str(e)},
            )
            raise HTTPException(
                status_code=http_status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Internal server error while retrieving workflow run",
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
        limit: int = Query(
            50,
            ge=1,
            le=AUDIT_EVENTS_MAX_PAGE_SIZE,
            description=f"Pagination limit (default 50, max {AUDIT_EVENTS_MAX_PAGE_SIZE})",
        ),
        eventTypes: str | None = Query(None, description="Filter by event types (comma-separated)", alias="eventTypes"),
        since: datetime | None = Query(None, description="ISO timestamp - events after this time"),
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
                events=result.events,
                total_count=result.total_count,
                offset=result.offset,
                limit=result.limit,
                has_next=result.has_next,
            )

        except ResourceNotFoundError as e:
            raise HTTPException(
                status_code=http_status.HTTP_404_NOT_FOUND,
                detail=str(e),
            )
        except HTTPException:
            raise
        except Exception as e:
            logger.error(
                "Unexpected error retrieving workflow run events",
                exc_info=True,
                extra={"workflow_run_id": workflow_run_id, "error": str(e)},
            )
            raise HTTPException(
                status_code=http_status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Internal server error while retrieving workflow run events",
            )

    # ========================================================================
    # Get Workflow Run Audit
    # ========================================================================

    @router.get(
        "/{workflow_run_id}/audit",
        response_model=WorkflowRunAuditResponse,
        summary="Get comprehensive workflow run audit",
        response_description="Complete audit information including events, stages, and validation",
    )
    async def get_workflow_run_audit(
        workflow_run_id: str,
        offset: int = Query(0, ge=0, description="Event pagination offset"),
        limit: int = Query(
            100,
            ge=1,
            le=AUDIT_EVENTS_MAX_PAGE_SIZE,
            description=f"Event pagination limit (default 100, max {AUDIT_EVENTS_MAX_PAGE_SIZE})",
        ),
        include_validation: bool = Query(True, description="Whether to validate event sequence (default True)"),
    ) -> WorkflowRunAuditResponse:
        """
        Get comprehensive audit information for a specific workflow run.

        **Parameters:**
        - workflow_run_id: Workflow run ID

        **Query Parameters:**
        - offset: Event pagination offset (default: 0)
        - limit: Event pagination limit (default: 100, max: 200)
        - include_validation: Whether to validate event sequence (default: True)

        **Returns:**
        - 200 OK: Complete audit information
        - 401 Unauthorized: Authentication required
        - 404 Not Found: Workflow run not found

        **Response includes:**
        - Workflow run summary with metadata
        - Paginated events list
        - Stage-grouped events with durations (always complete, not paginated)
        - Event sequence validation results (optional, expected vs actual)
        - Total event count and pagination metadata

        **Caching:**
        - Core audit data is cached for 5 minutes (default TTL)
        - Pagination and validation parameters are applied after retrieval
        - Cache key is based on workflow_run_id only

        **Performance:**
        - Optimized for workflows with 100-1000+ events
        - Pagination prevents memory issues on large workflows
        - Stage grouping and validation computed once and cached
        """
        try:
            # Get audit data via port
            audit_data = await query_port.get_workflow_run_audit(
                workflow_run_id=workflow_run_id,
                offset=offset,
                limit=limit,
                include_validation=include_validation,
            )

            # Convert to response DTO
            return WorkflowRunMapper.to_audit_response(audit_data)

        except ResourceNotFoundError as e:
            raise HTTPException(
                status_code=http_status.HTTP_404_NOT_FOUND,
                detail=str(e),
            )
        except HTTPException:
            raise
        except Exception as e:
            logger.error(
                "Unexpected error retrieving workflow run audit",
                exc_info=True,
                extra={"workflow_run_id": workflow_run_id, "error": str(e)},
            )
            raise HTTPException(
                status_code=http_status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Internal server error while retrieving workflow run audit",
            )

    return router
