"""
Executions REST API Router

Provides RESTful endpoints for execution monitoring including status,
logs, termination, and history with proper error handling for container
crashes, timeouts, and agent failures.
"""

from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status

from codetoreum.adapters.primary.execution_dtos import (
    ExecutionCommandResult,
    ExecutionHistoryResponse,
    ExecutionListResponse,
    ExecutionLogsResponse,
    ExecutionResponse,
    TerminateExecutionRequest,
)
from codetoreum.adapters.primary.execution_mappers import ExecutionMapper
from codetoreum.adapters.primary.simple_auth_dependencies import SimpleAuthDependencies
from codetoreum.domain.agent_execution import ExecutionStatus
from codetoreum.ports.input.execution_command import (
    IExecutionCommandPort,
    TerminateExecutionCommand,
)
from codetoreum.ports.input.execution_query import (
    ExecutionFilters,
    ExecutionPaginationParams,
    ExecutionSortField,
    IExecutionQueryPort,
    SortOrder,
)


def create_executions_router(
    command_port: IExecutionCommandPort,
    query_port: IExecutionQueryPort,
    auth_deps: Optional[SimpleAuthDependencies] = None,
) -> APIRouter:
    """
    Create the executions REST API router.

    Args:
        command_port: Execution command input port
        query_port: Execution query input port
        auth_deps: Optional authentication dependencies

    Returns:
        Configured APIRouter for executions
    """
    # Create router with authentication dependency if provided
    router_kwargs = {
        "prefix": "/api/v2/executions",
        "tags": ["executions"],
    }
    if auth_deps:
        router_kwargs["dependencies"] = [Depends(auth_deps.require_auth)]

    router = APIRouter(**router_kwargs)

    # ========================================================================
    # List Executions
    # ========================================================================

    @router.get(
        "",
        response_model=ExecutionListResponse,
        summary="List execution history with filtering",
        response_description="List of executions",
    )
    async def list_executions(
        status: Optional[str] = Query(None, description="Filter by status (pending, initialized, running, completed, failed, timeout, cancelled)"),
        agent_id: Optional[str] = Query(None, description="Filter by agent ID"),
        work_item_id: Optional[str] = Query(None, description="Filter by work item ID"),
        workflow_id: Optional[str] = Query(None, description="Filter by workflow ID"),
        stage_name: Optional[str] = Query(None, description="Filter by stage name"),
        start_date: Optional[str] = Query(None, description="Filter by start date (ISO 8601 format)"),
        end_date: Optional[str] = Query(None, description="Filter by end date (ISO 8601 format)"),
        offset: int = Query(0, ge=0, description="Offset for pagination"),
        limit: int = Query(20, ge=1, le=100, description="Limit for pagination (max 100)"),
        sort_by: str = Query("initialized_at", description="Sort field (initialized_at, started_at, completed_at, duration_seconds, status)"),
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

        **Examples:**
        - List all executions: `GET /api/v2/executions`
        - Filter by status: `GET /api/v2/executions?status=failed`
        - Filter by work item: `GET /api/v2/executions?work_item_id=wi-123`
        - Date range filter: `GET /api/v2/executions?start_date=2025-01-01&end_date=2025-01-31`
        - Combined filters: `GET /api/v2/executions?status=failed&work_item_id=wi-123`
        """
        try:
            # Parse status enum
            status_enum = None
            if status:
                try:
                    status_enum = ExecutionStatus(status.lower())
                except ValueError:
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
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
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail=f"Invalid start_date format: {start_date}. Use ISO 8601 format (e.g., '2025-01-01' or '2025-01-01T10:30:00Z')",
                    )

            if end_date:
                try:
                    end_date_dt = datetime.fromisoformat(end_date.replace("Z", "+00:00"))
                except ValueError:
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail=f"Invalid end_date format: {end_date}. Use ISO 8601 format (e.g., '2025-01-31' or '2025-01-31T23:59:59Z')",
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
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Invalid sort field: {sort_by}. Must be one of: initialized_at, started_at, completed_at, duration_seconds, status",
                )

            try:
                sort_order_enum = SortOrder(sort_order.lower())
            except ValueError:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
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

            # Calculate page number from offset/limit
            response.page = (offset // limit) + 1 if limit > 0 else 1

            return response

        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Failed to list executions: {str(e)}",
            )

    # ========================================================================
    # Get Execution Status
    # ========================================================================

    @router.get(
        "/{execution_id}",
        response_model=ExecutionResponse,
        summary="Get execution status and details",
        response_description="Execution status with error details if applicable",
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
            - Includes: container_id, exit_code, last_known_status
          - **EXECUTION_TIMEOUT**: Execution exceeded timeout
            - Includes: partial_logs_available flag
          - **AGENT_FAILURE**: Agent logic failure
            - Includes: complete logs available

        **Error Type Examples:**
        ```json
        // Container crash scenario
        {
          "status": "failed",
          "error_message": "Container exited unexpectedly",
          "error_detail": {
            "error_type": "CONTAINER_CRASHED",
            "message": "Container crashed with exit code 137 (OOM)",
            "container_status": {
              "container_id": "abc123",
              "last_known_status": "running",
              "exit_code": 137
            }
          }
        }

        // Timeout scenario
        {
          "status": "timeout",
          "error_message": "Execution exceeded timeout",
          "error_detail": {
            "error_type": "EXECUTION_TIMEOUT",
            "message": "Execution timed out after 300 seconds",
            "partial_logs_available": true
          }
        }

        // Agent failure scenario
        {
          "status": "failed",
          "error_message": "Agent logic error",
          "error_detail": {
            "error_type": "AGENT_FAILURE",
            "message": "Test suite failed with 3 failures",
            "partial_logs_available": false
          }
        }
        ```
        """
        try:
            # Get execution info
            execution_info = await query_port.get_execution(execution_id)

            # Convert to response DTO (includes error detail mapping)
            return ExecutionMapper.to_response(execution_info)

        except Exception as e:
            if "not found" in str(e).lower():
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"Execution not found: {str(e)}",
                )
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Failed to get execution: {str(e)}",
            )

    # ========================================================================
    # Get Execution Logs
    # ========================================================================

    @router.get(
        "/{execution_id}/logs",
        response_model=ExecutionLogsResponse,
        summary="Get execution logs",
        response_description="Container logs with timestamps and stage context",
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

        except Exception as e:
            if "not found" in str(e).lower():
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"Execution not found: {str(e)}",
                )
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Failed to get execution logs: {str(e)}",
            )

    # ========================================================================
    # Get Execution History
    # ========================================================================

    @router.get(
        "/{execution_id}/history",
        response_model=ExecutionHistoryResponse,
        summary="Get execution event history",
        response_description="Timeline of execution events",
    )
    async def get_execution_history(
        execution_id: str,
        limit: Optional[int] = Query(None, ge=1, le=1000, description="Limit number of events (max 1000)"),
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

        **Event Types:**
        - ExecutionInitialized
        - ExecutionStarted
        - ExecutionCompleted
        - ExecutionFailed
        - ExecutionTimeout
        - ContainerStarted
        - ContainerStopped
        - ContainerCrashed
        """
        try:
            # Get execution history
            history = await query_port.get_execution_history(
                execution_id=execution_id,
                limit=limit,
            )

            # Convert to response DTO
            return ExecutionMapper.to_history_response(history)

        except Exception as e:
            if "not found" in str(e).lower():
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"Execution not found: {str(e)}",
                )
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Failed to get execution history: {str(e)}",
            )

    # ========================================================================
    # Terminate Execution
    # ========================================================================

    @router.post(
        "/{execution_id}/terminate",
        response_model=ExecutionCommandResult,
        summary="Terminate running execution",
        response_description="Termination result",
    )
    async def terminate_execution(
        execution_id: str,
        request: TerminateExecutionRequest = TerminateExecutionRequest(),
    ) -> ExecutionCommandResult:
        """
        Terminate a running execution.

        This triggers:
        - Container termination (SIGTERM, then SIGKILL after grace period)
        - Workspace cleanup
        - Domain event emission (ExecutionTerminated)

        **Parameters:**
        - execution_id: Execution ID

        **Request Body (optional):**
        - reason: Optional reason for termination

        **Returns:**
        - 200 OK: Execution terminated successfully
        - 401 Unauthorized: Authentication required
        - 404 Not Found: Execution not found
        - 409 Conflict: Execution already completed

        **Note:**
        - Terminating an already completed execution returns 409 Conflict
        - Container receives SIGTERM first, then SIGKILL if it doesn't stop
        - Partial output may be available in logs
        - Event history preserved for audit trail
        """
        try:
            # Create command
            command = TerminateExecutionCommand(
                execution_id=execution_id,
                reason=request.reason,
            )

            # Execute command via port
            result = await command_port.terminate_execution(command)

            # Convert to response DTO
            return ExecutionMapper.to_command_result(result)

        except Exception as e:
            error_lower = str(e).lower()

            if "not found" in error_lower:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"Execution not found: {str(e)}",
                )
            elif "already completed" in error_lower or "invalid state" in error_lower:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail=f"Cannot terminate execution: {str(e)}",
                )
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Failed to terminate execution: {str(e)}",
            )

    return router
