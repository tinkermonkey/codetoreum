"""Manual trigger router for development and testing."""

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from codetoreum.adapters.primary.simple_auth_dependencies import SimpleAuthDependencies
from codetoreum.infrastructure.event_bus import EventBus
from codetoreum.ports.output.board_service import IBoardService, ColumnMovementResult, MovedByType

# Defaults match the codetoreum board setup constants (codetoreum_board_setup.py).
# Defined here as literals to avoid a circular import through the bootstrap package.
_DEFAULT_PROJECT_ID = "proj-codetoreum"
_DEFAULT_BOARD_ID = "board-codetoreum"


class TriggerColumnChangeRequest(BaseModel):
    work_item_id: str
    to_column: str
    from_column: str | None = None
    project_id: str = _DEFAULT_PROJECT_ID
    board_id: str = _DEFAULT_BOARD_ID


class TriggerColumnChangeResponse(BaseModel):
    work_item_id: str
    from_column: str | None
    to_column: str
    moved_by: str
    timestamp: str


def create_trigger_router(
    event_bus: EventBus,
    board_service: IBoardService | None = None,
    auth_deps: SimpleAuthDependencies | None = None,
) -> APIRouter:
    """Create the manual trigger router.

    Args:
        event_bus: In-process event bus to publish events to.
        board_service: Board service for moving items (required for functionality).
        auth_deps: Optional authentication dependencies.

    Returns:
        Configured APIRouter.
    """
    router_kwargs: dict[str, Any] = {
        "prefix": "/api/v2/trigger",
        "tags": ["trigger"],
    }
    if auth_deps:
        router_kwargs["dependencies"] = [Depends(auth_deps.require_auth)]

    router = APIRouter(**router_kwargs)

    @router.post(
        "/column-change",
        response_model=TriggerColumnChangeResponse,
        status_code=status.HTTP_200_OK,
        summary="Move a work item to a different column",
        response_description="Synchronous result of the column movement",
    )
    async def trigger_column_change(
        request: TriggerColumnChangeRequest,
    ) -> TriggerColumnChangeResponse:
        """
        Move a work item to a target column via the board service.

        Synchronously moves the item through IBoardService.move_item_to_column.
        The resulting WorkItemColumnChangedEvent is published to the event bus,
        triggering downstream handlers (lock acquisition, agent execution, etc.).

        **Request Body:**
        - work_item_id: Work item ID (required)
        - to_column: Target column name, e.g. "In Progress" (required)
        - from_column: Source column name (optional, for informational purposes)
        - project_id: Project ID (defaults to codetoreum project)
        - board_id: Board ID (defaults to codetoreum board)

        **Returns:**
        - 200 OK: Movement successful with result details
        - 400 Bad Request: Invalid parameters
        - 404 Not Found: Work item or column doesn't exist
        """
        if board_service is None:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Board service not available",
            )

        try:
            # Set board context for the board service (some adapters require it)
            await board_service.get_board(request.project_id, request.board_id)

            # Move the item synchronously
            result: ColumnMovementResult = await board_service.move_item_to_column(
                work_item_id=request.work_item_id,
                target_column=request.to_column,
                moved_by=MovedByType.ORCHESTRATOR,
            )

            return TriggerColumnChangeResponse(
                work_item_id=result.work_item_id,
                from_column=result.from_column,
                to_column=result.to_column,
                moved_by=result.moved_by.value,
                timestamp=result.timestamp,
            )
        except ValueError as e:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid parameters: {e!s}",
            ) from e
        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to move work item: {e!s}",
            ) from e

    return router
