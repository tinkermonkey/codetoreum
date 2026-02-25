"""
Orchestrator REST API Router

Provides RESTful endpoints for workflow orchestration operations including
starting, pausing, resuming, and canceling workflow executions.
"""


from fastapi import APIRouter, Depends, HTTPException, status

from codetoreum.adapters.primary.orchestration_dtos import (
    CancelWorkflowExecutionRequest,
    EntryConditionValidationRequest,
    EntryConditionValidationResponse,
    PauseWorkflowExecutionRequest,
    ResumeWorkflowExecutionRequest,
    StartWorkflowExecutionRequest,
    StartWorkflowExecutionResponse,
    WorkflowExecutionResponse,
)
from codetoreum.adapters.primary.simple_auth_dependencies import SimpleAuthDependencies
from codetoreum.adapters.primary.workflow_mappers import OrchestrationMapper
from codetoreum.ports.input.orchestration_command import (
    CancelExecutionCommand,
    IOrchestrationCommandPort,
    PauseExecutionCommand,
    ResumeExecutionCommand,
)


def create_orchestrator_router(
    orchestration_command_port: IOrchestrationCommandPort,
    auth_deps: SimpleAuthDependencies | None = None,
) -> APIRouter:
    """
    Create the orchestrator REST API router.

    Args:
        orchestration_command_port: Orchestration command input port
        auth_deps: Optional authentication dependencies

    Returns:
        Configured APIRouter for orchestrator
    """
    # Create router with authentication dependency if provided
    router_kwargs = {
        "prefix": "/api/v2/orchestrator",
        "tags": ["orchestrator"],
    }
    if auth_deps:
        router_kwargs["dependencies"] = [Depends(auth_deps.require_auth)]

    router = APIRouter(**router_kwargs)

    # ========================================================================
    # Start Workflow Execution
    # ========================================================================

    @router.post(
        "/start",
        response_model=StartWorkflowExecutionResponse,
        status_code=status.HTTP_202_ACCEPTED,
        summary="Start workflow execution for a work item",
        response_description="Execution started and queued",
    )
    async def start_workflow_execution(
        request: StartWorkflowExecutionRequest
    ) -> StartWorkflowExecutionResponse:
        """
        Start a workflow execution for a work item.

        This operation:
        1. Validates workflow and work item exist
        2. Checks entry conditions for the starting stage
        3. Creates a workflow run
        4. Queues the first agent execution
        5. Emits WorkflowStarted event
        6. Returns 202 Accepted with execution ID

        **Request Body:**
        - work_item_id: Work item ID to execute workflow for (required)
        - workflow_id: Workflow definition ID to use (required)
        - stage_name: Stage to start from (optional, defaults to first stage)
        - priority: Execution priority - LOW, MEDIUM, HIGH, CRITICAL (default: MEDIUM)
        - context: Additional execution context (optional)

        **Returns:**
        - 202 Accepted: Workflow execution queued successfully
        - 400 Bad Request: Invalid parameters or entry conditions not met
        - 401 Unauthorized: Authentication required
        - 404 Not Found: Workflow or work item not found

        **Entry Condition Validation:**
        If entry conditions are not met, returns 400 with details about
        which conditions are blocking execution.

        **Example:**
        ```json
        {
          "work_item_id": "wi-123",
          "workflow_id": "wf-456",
          "stage_name": null,
          "priority": "HIGH",
          "context": {
            "trigger": "manual",
            "user": "developer@example.com"
          }
        }
        ```
        """
        try:
            # Convert DTO to command
            command = OrchestrationMapper.to_start_execution_command(request)

            # Execute command via port
            result = await orchestration_command_port.start_execution(command)

            if not result.success:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail={
                        "message": result.message,
                        "errors": result.errors,
                    },
                )

            # Convert to response DTO
            return OrchestrationMapper.to_start_execution_response(result)

        except ValueError as e:
            # Invalid enum values or validation errors
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid request: {e!s}",
            )
        except Exception as e:
            # Domain errors
            error_msg = str(e).lower()
            if "not found" in error_msg:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=str(e),
                )
            if "entry condition" in error_msg or "condition not met" in error_msg:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Entry conditions not met: {e!s}",
                )
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=str(e),
            )

    # ========================================================================
    # Cancel Workflow Execution
    # ========================================================================

    @router.post(
        "/{workflow_run_id}/cancel",
        response_model=WorkflowExecutionResponse,
        summary="Cancel workflow execution",
        response_description="Cancellation result",
    )
    async def cancel_workflow_execution(
        workflow_run_id: str,
        request: CancelWorkflowExecutionRequest,
    ) -> WorkflowExecutionResponse:
        """
        Cancel an active workflow execution.

        **Parameters:**
        - workflow_run_id: Workflow run ID

        **Request Body:**
        - reason: Reason for cancellation (required)
        - force: Force immediate cancellation without cleanup (default: false)

        **Cancellation Behavior:**
        - If force=false (default): Current agent execution completes gracefully,
          no new executions started, cleanup tasks run
        - If force=true: Current agent execution terminated immediately,
          cleanup tasks may not run

        **Returns:**
        - 200 OK: Cancellation initiated successfully
        - 401 Unauthorized: Authentication required
        - 404 Not Found: Workflow run not found

        **Note:**
        - Emits WorkflowCancelled event
        - Work item status updated appropriately
        """
        try:
            # Create command
            command = CancelExecutionCommand(
                workflow_run_id=workflow_run_id,
                reason=request.reason,
                force=request.force,
            )

            # Execute command via port
            result = await orchestration_command_port.cancel_execution(command)

            if not result.success:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail={
                        "message": result.message,
                        "errors": result.errors,
                    },
                )

            # Convert to response DTO
            return OrchestrationMapper.to_execution_response(result)

        except Exception as e:
            # Domain errors
            if "not found" in str(e).lower():
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=str(e),
                )
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=str(e),
            )

    # ========================================================================
    # Pause Workflow Execution
    # ========================================================================

    @router.post(
        "/{workflow_run_id}/pause",
        response_model=WorkflowExecutionResponse,
        summary="Pause workflow execution",
        response_description="Pause result",
    )
    async def pause_workflow_execution(
        workflow_run_id: str,
        request: PauseWorkflowExecutionRequest,
    ) -> WorkflowExecutionResponse:
        """
        Pause an active workflow execution.

        Current agent execution completes, but no new executions are started
        until the workflow is resumed.

        **Parameters:**
        - workflow_run_id: Workflow run ID

        **Request Body:**
        - reason: Reason for pausing (required)

        **Returns:**
        - 200 OK: Workflow paused successfully
        - 400 Bad Request: Workflow not in pausable state
        - 401 Unauthorized: Authentication required
        - 404 Not Found: Workflow run not found

        **Note:**
        - Emits WorkflowPaused event
        - Workflow can be resumed later from the paused stage
        """
        try:
            # Create command
            command = PauseExecutionCommand(
                workflow_run_id=workflow_run_id,
                reason=request.reason,
            )

            # Execute command via port
            result = await orchestration_command_port.pause_execution(command)

            if not result.success:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail={
                        "message": result.message,
                        "errors": result.errors,
                    },
                )

            # Convert to response DTO
            return OrchestrationMapper.to_execution_response(result)

        except Exception as e:
            # Domain errors
            error_msg = str(e).lower()
            if "not found" in error_msg:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=str(e),
                )
            if "not active" in error_msg or "not pausable" in error_msg:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Workflow not in pausable state: {e!s}",
                )
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=str(e),
            )

    # ========================================================================
    # Resume Workflow Execution
    # ========================================================================

    @router.post(
        "/{workflow_run_id}/resume",
        response_model=WorkflowExecutionResponse,
        summary="Resume paused workflow execution",
        response_description="Resume result",
    )
    async def resume_workflow_execution(
        workflow_run_id: str,
        request: ResumeWorkflowExecutionRequest,
    ) -> WorkflowExecutionResponse:
        """
        Resume a paused workflow execution.

        Workflow continues from the stage it was paused at (or a specified stage).

        **Parameters:**
        - workflow_run_id: Workflow run ID

        **Request Body:**
        - from_stage: Stage to resume from (optional, defaults to paused stage)

        **Returns:**
        - 200 OK: Workflow resumed successfully
        - 400 Bad Request: Workflow not in paused state
        - 401 Unauthorized: Authentication required
        - 404 Not Found: Workflow run not found

        **Note:**
        - Emits WorkflowResumed event
        - Agent execution queued for the resume stage
        """
        try:
            # Create command
            command = ResumeExecutionCommand(
                workflow_run_id=workflow_run_id,
                from_stage=request.from_stage,
            )

            # Execute command via port
            result = await orchestration_command_port.resume_execution(command)

            if not result.success:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail={
                        "message": result.message,
                        "errors": result.errors,
                    },
                )

            # Convert to response DTO
            return OrchestrationMapper.to_execution_response(result)

        except Exception as e:
            # Domain errors
            error_msg = str(e).lower()
            if "not found" in error_msg:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=str(e),
                )
            if "not paused" in error_msg:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Workflow not in paused state: {e!s}",
                )
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=str(e),
            )

    # ========================================================================
    # Validate Entry Conditions
    # ========================================================================

    @router.post(
        "/validate-entry-conditions",
        response_model=EntryConditionValidationResponse,
        summary="Validate workflow entry conditions",
        response_description="Validation result",
    )
    async def validate_entry_conditions(
        request: EntryConditionValidationRequest
    ) -> EntryConditionValidationResponse:
        """
        Check whether entry conditions are met for starting a workflow.

        This can be called before attempting to start a workflow to validate
        that all entry conditions are satisfied.

        **Request Body:**
        - work_item_id: Work item ID to check (required)
        - workflow_id: Workflow ID to check conditions for (required)
        - stage_name: Specific stage to check (optional, defaults to first stage)

        **Returns:**
        - 200 OK: Validation result
        - 401 Unauthorized: Authentication required
        - 404 Not Found: Workflow or work item not found

        **Response includes:**
        - can_start: Whether workflow can be started
        - stage_name: Stage that was validated
        - condition_results: Results for each condition
        - blocking_conditions: List of conditions that are not met

        **Example Response:**
        ```json
        {
          "can_start": false,
          "stage_name": "development",
          "condition_results": [
            {
              "condition_type": "work_item_status",
              "is_met": false,
              "message": "Work item status must be 'in_progress' but is 'new'",
              "details": {"expected": "in_progress", "actual": "new"}
            }
          ],
          "blocking_conditions": ["work_item_status"]
        }
        ```
        """
        try:
            # Check entry conditions via port
            check_result = await orchestration_command_port.check_entry_conditions(
                work_item_id=request.work_item_id,
                workflow_id=request.workflow_id,
                stage_name=request.stage_name,
            )

            # Convert to response DTO
            return OrchestrationMapper.to_entry_condition_validation_response(check_result)

        except Exception as e:
            # Domain errors
            if "not found" in str(e).lower():
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=str(e),
                )
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=str(e),
            )

    return router
