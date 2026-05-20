"""Manual trigger router for development and testing."""

from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from codetoreum.adapters.primary.simple_auth_dependencies import SimpleAuthDependencies
from codetoreum.domain.events.board_events import WorkItemColumnChangedEvent
from codetoreum.infrastructure.event_bus import EventBus

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
    event_id: str
    work_item_id: str
    to_column: str
    status: str


def create_trigger_router(
    event_bus: EventBus,
    auth_deps: SimpleAuthDependencies | None = None,
) -> APIRouter:
    """Create the manual trigger router.

    Args:
        event_bus: In-process event bus to publish events to.
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
        status_code=status.HTTP_202_ACCEPTED,
        summary="Manually trigger a work item column change",
        response_description="Event published to the in-process event bus",
    )
    async def trigger_column_change(
        request: TriggerColumnChangeRequest,
    ) -> TriggerColumnChangeResponse:
        """
        Publish a WorkItemColumnChangedEvent directly to the in-process event bus.

        Fires the same event path as a GitHub project-card webhook without requiring
        GitHub integration. Intended for development and CLI-based triggering.

        **Request Body:**
        - work_item_id: GitHub issue number or internal ID (required)
        - to_column: Target column name, e.g. "In Progress" (required)
        - from_column: Source column name (optional, null for initial placement)
        - project_id: Project ID (defaults to codetoreum project)
        - board_id: Board ID (defaults to codetoreum board)

        **Returns:**
        - 202 Accepted: Event published successfully
        - 400 Bad Request: Invalid event parameters
        """
        try:
            event = WorkItemColumnChangedEvent(
                type="workitem.column_changed",
                timestamp=datetime.now(UTC).isoformat(),
                source="trigger_api",
                work_item_id=request.work_item_id,
                project_id=request.project_id,
                board_id=request.board_id,
                from_column=request.from_column,
                to_column=request.to_column,
                moved_by="orchestrator",
            )
            await event_bus.publish(event)
            return TriggerColumnChangeResponse(
                event_id=getattr(event, "event_id", ""),
                work_item_id=request.work_item_id,
                to_column=request.to_column,
                status="published",
            )
        except ValueError as e:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid event parameters: {e!s}",
            ) from e
        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to publish event: {e!s}",
            ) from e

    return router
