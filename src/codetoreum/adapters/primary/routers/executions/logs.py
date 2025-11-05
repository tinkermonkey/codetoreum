"""
Execution Logs Endpoints

Handles retrieving container logs for executions.
"""

from typing import Optional

from fastapi import APIRouter, HTTPException, Query
from fastapi import status as http_status

from codetoreum.adapters.primary.execution_dtos import ExecutionLogsResponse
from codetoreum.adapters.primary.execution_mappers import ExecutionMapper
from codetoreum.ports.input.execution_query import IExecutionQueryPort


def register_logs_endpoints(
    router: APIRouter,
    query_port: IExecutionQueryPort,
) -> None:
    """Register execution logs endpoints on the router."""

    @router.get(
        "/{execution_id}/logs",
        response_model=ExecutionLogsResponse,
        summary="Get execution logs",
        response_description="Container logs with timestamps and stage context",
        responses={
            200: {"description": "Execution logs with timestamps"},
            401: {"description": "Unauthorized - Authentication required"},
            404: {"description": "Not Found - Execution not found"},
        },
    )
    async def get_execution_logs(
        execution_id: str,
        stage: Optional[str] = Query(None, description="Filter logs by stage name"),
        tail: Optional[int] = Query(None, ge=1, le=10000, description="Return last N lines (max 10000)"),
    ) -> ExecutionLogsResponse:
        """
        Get container logs for an execution.

        **Parameters:**
        - execution_id: Execution ID

        **Query Parameters:**
        - stage: Optional filter by stage name
        - tail: Optional limit to last N lines (max 10000)

        **Returns:**
        - 200 OK: Execution logs with timestamps
        - 401 Unauthorized: Authentication required
        - 404 Not Found: Execution not found

        **Response includes:**
        - Log entries with timestamps and levels
        - Stage context for each log entry
        - Total line count
        - Flag indicating if more logs are available

        **Examples:**
        - Get all logs: `GET /api/v2/executions/{id}/logs`
        - Get last 100 lines: `GET /api/v2/executions/{id}/logs?tail=100`
        - Filter by stage: `GET /api/v2/executions/{id}/logs?stage=test`
        - Combined: `GET /api/v2/executions/{id}/logs?stage=test&tail=100`

        **Note:** For container crash scenarios, logs may be incomplete.
        Check the `has_more` flag and `error_detail.partial_logs_available`
        from the execution status endpoint.
        """
        try:
            # Get execution logs
            logs = await query_port.get_execution_logs(
                execution_id=execution_id,
                stage=stage,
                tail=tail,
            )

            # Convert to response DTO
            return ExecutionMapper.to_logs_response(logs)

        except (ValueError, KeyError, AttributeError) as e:
            if "not found" in str(e).lower():
                raise HTTPException(
                    status_code=http_status.HTTP_404_NOT_FOUND,
                    detail=f"Execution not found: {str(e)}",
                )
            raise HTTPException(
                status_code=http_status.HTTP_400_BAD_REQUEST,
                detail=f"Failed to get execution logs: {str(e)}",
            )
