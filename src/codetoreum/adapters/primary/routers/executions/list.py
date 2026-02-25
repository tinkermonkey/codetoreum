"""
Execution List Endpoints

Handles listing and filtering executions.
"""

from datetime import datetime

from fastapi import APIRouter, HTTPException, Query
from fastapi import status as http_status

from codetoreum.adapters.primary.execution_dtos import ExecutionListResponse
from codetoreum.adapters.primary.execution_mappers import ExecutionMapper
from codetoreum.config import DEFAULT_OFFSET, DEFAULT_PAGE_SIZE, MAX_PAGE_SIZE
from codetoreum.domain.agent_execution import ExecutionStatus
from codetoreum.ports.input.execution_query import (
    ExecutionFilters,
    ExecutionPaginationParams,
    ExecutionSortField,
    IExecutionQueryPort,
    SortOrder,
)


def register_list_endpoints(
    router: APIRouter,
    query_port: IExecutionQueryPort,
) -> None:
    """Register execution list endpoints on the router."""

    @router.get(
        "",
        response_model=ExecutionListResponse,
        summary="List execution history with filtering",
        response_description="List of executions",
        responses={
            200: {"description": "List of executions with pagination metadata"},
            400: {"description": "Bad Request - Invalid filter parameters"},
            401: {"description": "Unauthorized - Authentication required"},
        },
    )
    async def list_executions(
        status: str | None = Query(
            None,
            description="Filter by status (pending, initialized, running, completed, failed, timeout, cancelled)",
        ),
        agent_id: str | None = Query(None, description="Filter by agent ID"),
        work_item_id: str | None = Query(None, description="Filter by work item ID"),
        workflow_id: str | None = Query(None, description="Filter by workflow ID"),
        stage_name: str | None = Query(None, description="Filter by stage name"),
        start_date: str | None = Query(None, description="Filter by start date (ISO 8601 format)"),
        end_date: str | None = Query(None, description="Filter by end date (ISO 8601 format)"),
        offset: int = Query(DEFAULT_OFFSET, ge=0, description="Offset for pagination"),
        limit: int = Query(
            DEFAULT_PAGE_SIZE,
            ge=1,
            le=MAX_PAGE_SIZE,
            description=f"Limit for pagination (max {MAX_PAGE_SIZE})",
        ),
        sort_by: str = Query(
            "initialized_at",
            description="Sort field (initialized_at, started_at, completed_at, duration_seconds, status)",
        ),
        sort_order: str = Query("desc", description="Sort order (asc, desc)"),
    ) -> ExecutionListResponse:
        """
        List executions with optional filtering and pagination.

        **Query Parameters:**
        - status: Filter by status (pending, initialized, running, completed, failed, timeout, cancelled)
        - agent_id: Filter by agent ID
        - work_item_id: Filter by work item ID
        - workflow_id: Filter by workflow ID
        - stage_name: Filter by stage name
        - start_date: Filter by start date (ISO 8601 format, e.g., "2025-01-01")
        - end_date: Filter by end date (ISO 8601 format, e.g., "2025-01-31")
        - offset: Pagination offset (default: 0)
        - limit: Pagination limit (default: 20, max: 100)
        - sort_by: Sort field (initialized_at, started_at, completed_at, duration_seconds, status)
        - sort_order: Sort order (asc, desc)

        **Returns:**
        - 200 OK: List of executions with pagination metadata and error types
        - 400 Bad Request: Invalid filter parameters
        - 401 Unauthorized: Authentication required
        """
        try:
            # Parse status enum
            status_enum = None
            if status:
                try:
                    status_enum = ExecutionStatus(status.lower())
                except ValueError:
                    raise HTTPException(
                        status_code=http_status.HTTP_400_BAD_REQUEST,
                        detail=f"Invalid status: {status}. Must be one of: pending, initialized, running, completed, failed, timeout, cancelled",
                    )

            # Parse dates
            start_date_dt = None
            end_date_dt = None
            if start_date:
                try:
                    start_date_dt = datetime.fromisoformat(start_date.replace("Z", "+00:00"))
                except ValueError:
                    raise HTTPException(
                        status_code=http_status.HTTP_400_BAD_REQUEST,
                        detail=f"Invalid start_date format: {start_date}. Use ISO 8601 format",
                    )

            if end_date:
                try:
                    end_date_dt = datetime.fromisoformat(end_date.replace("Z", "+00:00"))
                except ValueError:
                    raise HTTPException(
                        status_code=http_status.HTTP_400_BAD_REQUEST,
                        detail=f"Invalid end_date format: {end_date}. Use ISO 8601 format",
                    )

            # Validate date range
            if start_date_dt and end_date_dt and start_date_dt >= end_date_dt:
                raise HTTPException(
                    status_code=http_status.HTTP_400_BAD_REQUEST,
                    detail="Invalid date range: start_date must be before end_date",
                )

            # Parse filters
            filters = ExecutionFilters(
                status=status_enum,
                agent_id=agent_id,
                work_item_id=work_item_id,
                workflow_id=workflow_id,
                stage_name=stage_name,
                start_date=start_date_dt,
                end_date=end_date_dt,
            )

            # Parse pagination
            try:
                sort_field = ExecutionSortField(sort_by.lower())
            except ValueError:
                raise HTTPException(
                    status_code=http_status.HTTP_400_BAD_REQUEST,
                    detail=f"Invalid sort field: {sort_by}. Must be one of: initialized_at, started_at, completed_at, duration_seconds, status",
                )

            try:
                sort_order_enum = SortOrder(sort_order.lower())
            except ValueError:
                raise HTTPException(
                    status_code=http_status.HTTP_400_BAD_REQUEST,
                    detail=f"Invalid sort order: {sort_order}. Must be asc or desc",
                )

            pagination = ExecutionPaginationParams(
                offset=offset,
                limit=limit,
                sort_by=sort_field,
                sort_order=sort_order_enum,
            )

            # Execute query via port
            result = await query_port.list_executions(filters, pagination)

            # Convert to response DTO
            response = ExecutionMapper.to_list_response(result)

            # Calculate page number from offset/limit and set page_size
            response.page = (offset // limit) + 1 if limit > 0 else 1
            response.page_size = limit

            return response

        except HTTPException:
            raise
        except (ValueError, KeyError, AttributeError) as e:
            raise HTTPException(
                status_code=http_status.HTTP_400_BAD_REQUEST,
                detail=f"Failed to list executions: {e!s}",
            )
