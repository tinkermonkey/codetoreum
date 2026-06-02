"""Diagnostics router for system operations and maintenance."""

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from codetoreum.adapters.primary.simple_auth_dependencies import SimpleAuthDependencies
from codetoreum.ports.output.board_service import BoardConfig, IBoardService, ReconciliationResult
from codetoreum.ports.output.workflow_config_service import IWorkflowConfigService


class BoardReconcileRequest(BaseModel):
    """Request to reconcile a board with its configuration."""

    auto_create_missing: bool = True


class BoardReconcileResponse(BaseModel):
    """Response with board reconciliation results."""

    board_id: str
    columns_added: list[str]
    columns_removed: list[str]
    columns_renamed: list[tuple[str, str]]
    orphaned_items: list[str]
    status: str


def create_diagnostics_router(
    board_service: IBoardService | None = None,
    workflow_config: IWorkflowConfigService | None = None,
    auth_deps: SimpleAuthDependencies | None = None,
) -> APIRouter:
    """Create the diagnostics router.

    Args:
        board_service: Board service for board operations (required for functionality).
        workflow_config: Workflow configuration service (required for functionality).
        auth_deps: Optional authentication dependencies.

    Returns:
        Configured APIRouter.
    """
    router_kwargs: dict[str, Any] = {
        "prefix": "/api/v2/diagnostics",
        "tags": ["diagnostics"],
    }
    if auth_deps:
        router_kwargs["dependencies"] = [Depends(auth_deps.require_auth)]

    router = APIRouter(**router_kwargs)

    @router.post(
        "/boards/{board_id}/reconcile",
        response_model=BoardReconcileResponse,
        status_code=status.HTTP_200_OK,
        summary="Reconcile board structure with configuration",
        response_description="Results of board reconciliation",
    )
    async def reconcile_board(
        board_id: str,
        request: BoardReconcileRequest,
    ) -> BoardReconcileResponse:
        """
        Reconcile a board's structure with its expected configuration.

        Creates missing columns, reports extra columns, and validates board state.
        This is a maintenance operation that ensures boards stay in sync with
        their workflow configuration.

        **Path Parameters:**
        - board_id: ID of the board to reconcile

        **Request Body:**
        - auto_create_missing: If true, create missing columns. If false, only report. (default: true)

        **Returns:**
        - 200 OK: Reconciliation completed with results
        - 400 Bad Request: Invalid parameters
        - 404 Not Found: Board doesn't exist
        """
        if board_service is None or workflow_config is None:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Required services not available",
            )

        try:
            # Get the workflow template for the board to find expected columns
            board_config = await workflow_config.get_board_workflow_template(board_id)
            if not board_config:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"No workflow configuration found for board {board_id}",
                )

            # Extract column names from the template
            expected_columns = [col.name for col in board_config.columns]

            # Create reconciliation config
            recon_config = BoardConfig(
                board_id=board_id,
                expected_columns=tuple(expected_columns),
                auto_create_missing=request.auto_create_missing,
            )

            # Perform reconciliation
            result: ReconciliationResult = await board_service.reconcile_board(board_id, recon_config)

            return BoardReconcileResponse(
                board_id=result.board_id,
                columns_added=list(result.columns_added),
                columns_removed=list(result.columns_removed),
                columns_renamed=list(result.columns_renamed),
                orphaned_items=list(result.orphaned_items),
                status="success",
            )
        except HTTPException:
            raise
        except ValueError as e:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid parameters: {e!s}",
            ) from e
        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Board reconciliation failed: {e!s}",
            ) from e

    return router
