"""
Execution Detail Endpoints

Handles retrieving detailed execution status and history.
"""


from fastapi import APIRouter, HTTPException, Query
from fastapi import status as http_status

from codetoreum.adapters.primary.execution_dtos import (
    ExecutionHistoryResponse,
    ExecutionResponse,
)
from codetoreum.adapters.primary.execution_mappers import ExecutionMapper
from codetoreum.ports.input.execution_query import IExecutionQueryPort


def register_detail_endpoints(
    router: APIRouter,
    query_port: IExecutionQueryPort,
) -> None:
    """Register execution detail endpoints on the router."""

    @router.get(
        "/{execution_id}",
        response_model=ExecutionResponse,
        summary="Get execution status and details",
        response_description="Execution status with error details if applicable",
        responses={
            200: {"description": "Execution status with comprehensive error details"},
            401: {"description": "Unauthorized - Authentication required"},
            404: {"description": "Not Found - Execution not found"},
        },
    )
    async def get_execution(execution_id: str) -> ExecutionResponse:
        """
        Get detailed status information about a specific execution.

        **Parameters:**
        - execution_id: Execution ID

        **Returns:**
        - 200 OK: Execution status with comprehensive error details
        - 401 Unauthorized: Authentication required
        - 404 Not Found: Execution not found

        **Response includes:**
        - Current status and stage
        - Elapsed time and duration
        - Input/output token counts
        - Output and error messages
        - Detailed error information with error_type:
          - **CONTAINER_CRASHED**: Container exited unexpectedly
          - **EXECUTION_TIMEOUT**: Execution exceeded timeout
          - **AGENT_FAILURE**: Agent logic failure
        """
        try:
            # Get execution info
            execution_info = await query_port.get_execution(execution_id)

            # Convert to response DTO (includes error detail mapping)
            return ExecutionMapper.to_response(execution_info)

        except (ValueError, KeyError, AttributeError) as e:
            if "not found" in str(e).lower():
                raise HTTPException(
                    status_code=http_status.HTTP_404_NOT_FOUND,
                    detail=f"Execution not found: {str(e)}",
                )
            raise HTTPException(
                status_code=http_status.HTTP_400_BAD_REQUEST,
                detail=f"Failed to get execution: {str(e)}",
            )

    @router.get(
        "/{execution_id}/history",
        response_model=ExecutionHistoryResponse,
        summary="Get execution event history",
        response_description="Timeline of execution events",
        responses={
            200: {"description": "Execution event history with timeline"},
            401: {"description": "Unauthorized - Authentication required"},
            404: {"description": "Not Found - Execution not found"},
        },
    )
    async def get_execution_history(
        execution_id: str,
        limit: int | None = Query(None, ge=1, le=1000, description="Limit number of events (max 1000)"),
    ) -> ExecutionHistoryResponse:
        """
        Get event history timeline for an execution.

        **Parameters:**
        - execution_id: Execution ID

        **Query Parameters:**
        - limit: Optional limit on number of events (max 1000)

        **Returns:**
        - 200 OK: Execution event history with timeline
        - 401 Unauthorized: Authentication required
        - 404 Not Found: Execution not found

        **Response includes:**
        - Event type (ExecutionInitialized, ExecutionStarted, ExecutionCompleted, etc.)
        - Timestamp for each event
        - Event payload with context
        - Total event count
        """
        try:
            # Get execution history
            history = await query_port.get_execution_history(
                execution_id=execution_id,
                limit=limit,
            )

            # Convert to response DTO
            return ExecutionMapper.to_history_response(history)

        except (ValueError, KeyError, AttributeError) as e:
            if "not found" in str(e).lower():
                raise HTTPException(
                    status_code=http_status.HTTP_404_NOT_FOUND,
                    detail=f"Execution not found: {str(e)}",
                )
            raise HTTPException(
                status_code=http_status.HTTP_400_BAD_REQUEST,
                detail=f"Failed to get execution history: {str(e)}",
            )
