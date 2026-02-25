"""
Execution Control Endpoints

Handles execution lifecycle control operations (terminate, pause, resume, etc.).
"""

from fastapi import APIRouter, HTTPException
from fastapi import status as http_status

from codetoreum.adapters.primary.execution_dtos import (
    ExecutionCommandResult,
    TerminateExecutionRequest,
)
from codetoreum.adapters.primary.execution_mappers import ExecutionMapper
from codetoreum.infrastructure.audit import get_audit_logger
from codetoreum.ports.input.execution_command import (
    IExecutionCommandPort,
    TerminateExecutionCommand,
)


def register_control_endpoints(
    router: APIRouter,
    command_port: IExecutionCommandPort,
) -> None:
    """Register execution control endpoints on the router."""

    @router.post(
        "/{execution_id}/terminate",
        response_model=ExecutionCommandResult,
        summary="Terminate running execution",
        response_description="Termination result",
        responses={
            200: {"description": "Execution terminated successfully"},
            401: {"description": "Unauthorized - Authentication required"},
            404: {"description": "Not Found - Execution not found"},
            409: {"description": "Conflict - Execution already completed"},
        },
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
        audit_logger = get_audit_logger()

        try:
            # Create command
            command = TerminateExecutionCommand(
                execution_id=execution_id,
                reason=request.reason,
            )

            # Execute command via port
            result = await command_port.terminate_execution(command)

            # Log successful execution termination
            audit_logger.log_execution_terminated(
                execution_id=execution_id,
                user_id="api-user",
                reason=request.reason,
                success=True,
            )

            # Convert to response DTO
            return ExecutionMapper.to_command_result(result)

        except (ValueError, KeyError, AttributeError) as e:
            error_lower = str(e).lower()

            # Log failed execution termination
            audit_logger.log_execution_terminated(
                execution_id=execution_id,
                user_id="api-user",
                reason=request.reason,
                success=False,
            )

            if "not found" in error_lower:
                raise HTTPException(
                    status_code=http_status.HTTP_404_NOT_FOUND,
                    detail=f"Execution not found: {e!s}",
                )
            if "already completed" in error_lower or "invalid state" in error_lower:
                raise HTTPException(
                    status_code=http_status.HTTP_409_CONFLICT,
                    detail=f"Cannot terminate execution: {e!s}",
                )
            raise HTTPException(
                status_code=http_status.HTTP_400_BAD_REQUEST,
                detail=f"Failed to terminate execution: {e!s}",
            )
