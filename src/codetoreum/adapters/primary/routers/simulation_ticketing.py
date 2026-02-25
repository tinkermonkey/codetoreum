"""
Simulation Ticketing REST API Router

Provides simulation-only endpoints for creating issues, moving cards between
columns, adding comments, and viewing board state. These endpoints drive the
workflow pipeline from the "outside" — simulating human ticketing actions.

This router is ONLY mounted in SimulationApplicationBootstrap, never in production.
"""

import logging
from typing import Any

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field

from codetoreum.adapters.testing.in_memory_ticket_adapter import InMemoryTicketAdapter
from codetoreum.adapters.testing.mock_board_adapter import MockBoardAdapter
from codetoreum.domain.work_item import WorkItemPriority
from codetoreum.ports.output.board_service import MovedByType

logger = logging.getLogger(__name__)

# =========================================================================
# Request/Response DTOs
# =========================================================================


class SimCreateIssueRequest(BaseModel):
    """Request to create a new issue."""

    title: str = Field(..., description="Issue title", min_length=1)
    description: str = Field(default="", description="Issue description")
    project_id: str = Field(..., description="Project ID")
    labels: list[str] = Field(default_factory=list, description="Labels")
    priority: str = Field(default="medium", description="Priority: low, medium, high, critical")
    board_id: str | None = Field(None, description="Board to place issue on")
    column: str | None = Field(None, description="Column to place issue in (requires board_id)")


class SimMoveIssueRequest(BaseModel):
    """Request to move an issue between columns."""

    target_column: str = Field(..., description="Target column name")


class SimAddCommentRequest(BaseModel):
    """Request to add a comment to an issue."""

    body: str = Field(..., description="Comment body", min_length=1)
    author: str = Field(default="simulation-user", description="Comment author")


class SimIssueResponse(BaseModel):
    """Issue response."""

    id: str
    title: str
    description: str
    project_id: str
    status: str
    priority: str
    labels: list[str]
    created_at: str
    external_id: str | None = None
    board_position: dict[str, Any] | None = None


class SimIssueListResponse(BaseModel):
    """List of issues response."""

    issues: list[SimIssueResponse]
    total: int


class SimMoveResponse(BaseModel):
    """Move result response."""

    work_item_id: str
    from_column: str
    to_column: str
    moved_by: str
    timestamp: str


class SimCommentResponse(BaseModel):
    """Comment added response."""

    id: str
    work_item_id: str
    body: str
    author: str
    created_at: str


class SimBoardColumnResponse(BaseModel):
    """Board column response."""

    name: str
    position: int
    item_count: int
    work_item_ids: list[str]


class SimBoardColumnsResponse(BaseModel):
    """Board columns list response."""

    board_id: str
    board_name: str
    columns: list[SimBoardColumnResponse]


class SimBoardItemResponse(BaseModel):
    """Board item position response."""

    work_item_id: str
    column_name: str
    position: int


class SimBoardItemsResponse(BaseModel):
    """All board items response."""

    board_id: str
    items: list[SimBoardItemResponse]
    total: int


class SimMovementHistoryEntry(BaseModel):
    """Movement history entry."""

    work_item_id: str
    from_column: str | None
    to_column: str
    moved_by: str
    timestamp: str


class SimBoardHistoryResponse(BaseModel):
    """Board movement history response."""

    board_id: str
    movements: list[SimMovementHistoryEntry]
    total: int


# =========================================================================
# Router Factory
# =========================================================================


def create_simulation_ticketing_router(
    ticket_adapter: InMemoryTicketAdapter,
    board_adapter: MockBoardAdapter,
) -> APIRouter:
    """
    Create the simulation ticketing router.

    This router provides simulation-only endpoints for driving the workflow
    pipeline from outside. It takes mock adapters directly (not port interfaces)
    because this is simulation infrastructure, not production code.

    Args:
        ticket_adapter: In-memory ticket system adapter
        board_adapter: Mock board adapter

    Returns:
        Configured APIRouter for simulation ticketing
    """
    router = APIRouter(
        prefix="/api/v2/simulation/ticketing",
        tags=["simulation-ticketing"],
    )

    # =====================================================================
    # Issue Endpoints
    # =====================================================================

    @router.post("/issues", response_model=SimIssueResponse, status_code=status.HTTP_201_CREATED)
    async def create_issue(request: SimCreateIssueRequest):
        """Create a new issue and optionally place it on a board."""
        priority_map = {
            "low": WorkItemPriority.LOW,
            "medium": WorkItemPriority.MEDIUM,
            "high": WorkItemPriority.HIGH,
            "critical": WorkItemPriority.CRITICAL,
        }
        priority = priority_map.get(request.priority.lower())
        if priority is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid priority: {request.priority}. Valid: low, medium, high, critical",
            )

        work_item = await ticket_adapter.create_work_item(
            title=request.title,
            description=request.description,
            project_id=request.project_id,
            labels=request.labels,
            priority=priority,
        )

        board_position = None
        if request.board_id and request.column:
            try:
                board_adapter.current_project = request.project_id
                board_adapter.add_item_to_column(request.board_id, request.column, work_item.id)
                board_position = {
                    "board_id": request.board_id,
                    "column": request.column,
                }
            except ValueError as e:
                logger.warning(f"Failed to place item on board: {e}")

        return SimIssueResponse(
            id=work_item.id,
            title=work_item.title,
            description=work_item.description,
            project_id=work_item.project_id,
            status=work_item.status.value,
            priority=work_item.priority.name.lower(),
            labels=work_item.labels,
            created_at=work_item.created_at.isoformat(),
            external_id=work_item.external_id,
            board_position=board_position,
        )

    @router.get("/issues", response_model=SimIssueListResponse)
    async def list_issues(project_id: str | None = None):
        """List all issues, optionally filtered by project_id."""
        items = await ticket_adapter.list_work_items(project_id=project_id)
        issues = [
            SimIssueResponse(
                id=item.id,
                title=item.title,
                description=item.description,
                project_id=item.project_id,
                status=item.status.value,
                priority=item.priority.name.lower(),
                labels=item.labels,
                created_at=item.created_at.isoformat(),
                external_id=item.external_id,
            )
            for item in items
        ]
        return SimIssueListResponse(issues=issues, total=len(issues))

    @router.get("/issues/{issue_id}", response_model=SimIssueResponse)
    async def get_issue(issue_id: str):
        """Get issue details by ID."""
        try:
            item = await ticket_adapter.get_work_item(issue_id)
        except Exception:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Issue not found: {issue_id}",
            )

        # Try to get board position
        board_position = None
        try:
            pos = await board_adapter.get_item_position(issue_id)
            board_position = {
                "column": pos.column_name,
                "position": pos.position,
            }
        except ValueError:
            pass

        return SimIssueResponse(
            id=item.id,
            title=item.title,
            description=item.description,
            project_id=item.project_id,
            status=item.status.value,
            priority=item.priority.name.lower(),
            labels=item.labels,
            created_at=item.created_at.isoformat(),
            external_id=item.external_id,
            board_position=board_position,
        )

    # =====================================================================
    # Board Action Endpoints
    # =====================================================================

    @router.post("/issues/{issue_id}/move", response_model=SimMoveResponse)
    async def move_issue(issue_id: str, request: SimMoveIssueRequest):
        """Move an issue between board columns (simulates human drag-and-drop)."""
        # Verify issue exists
        try:
            item = await ticket_adapter.get_work_item(issue_id)
        except Exception:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Issue not found: {issue_id}",
            )

        # Set project context from the work item
        board_adapter.current_project = item.project_id

        try:
            result = await board_adapter.move_item_to_column(issue_id, request.target_column, MovedByType.HUMAN)
        except ValueError as e:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=str(e),
            )

        return SimMoveResponse(
            work_item_id=result.work_item_id,
            from_column=result.from_column,
            to_column=result.to_column,
            moved_by=result.moved_by.value,
            timestamp=result.timestamp,
        )

    @router.post("/issues/{issue_id}/comment", response_model=SimCommentResponse)
    async def add_comment(issue_id: str, request: SimAddCommentRequest):
        """Add a comment to an issue."""
        # Verify issue exists
        try:
            await ticket_adapter.get_work_item(issue_id)
        except Exception:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Issue not found: {issue_id}",
            )

        comment = await ticket_adapter.add_comment(
            item_id=issue_id,
            body=request.body,
            author=request.author,
        )

        return SimCommentResponse(
            id=comment.id,
            work_item_id=issue_id,
            body=comment.body,
            author=comment.author_id,
            created_at=comment.created_at.isoformat(),
        )

    # =====================================================================
    # Board View Endpoints
    # =====================================================================

    @router.get("/board/{board_id}/columns", response_model=SimBoardColumnsResponse)
    async def get_board_columns(board_id: str, project_id: str):
        """View board columns with item counts."""
        board_adapter.current_project = project_id

        try:
            board = await board_adapter.get_board(project_id, board_id)
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Board not found: {board_id}",
            )

        columns = [
            SimBoardColumnResponse(
                name=col.name,
                position=col.position,
                item_count=len(col.work_item_ids),
                work_item_ids=col.work_item_ids,
            )
            for col in sorted(board.columns, key=lambda c: c.position)
        ]

        return SimBoardColumnsResponse(
            board_id=board.id,
            board_name=board.name,
            columns=columns,
        )

    @router.get("/board/{board_id}/items", response_model=SimBoardItemsResponse)
    async def get_board_items(board_id: str, project_id: str):
        """View all items and their positions on a board."""
        board_adapter.current_project = project_id

        try:
            board = await board_adapter.get_board(project_id, board_id)
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Board not found: {board_id}",
            )

        items = []
        for col in board.columns:
            for idx, item_id in enumerate(col.work_item_ids):
                items.append(
                    SimBoardItemResponse(
                        work_item_id=item_id,
                        column_name=col.name,
                        position=idx,
                    )
                )

        return SimBoardItemsResponse(
            board_id=board.id,
            items=items,
            total=len(items),
        )

    @router.get("/board/{board_id}/history", response_model=SimBoardHistoryResponse)
    async def get_board_history(board_id: str):
        """View movement audit trail for a board."""
        movements = [
            SimMovementHistoryEntry(
                work_item_id=m.work_item_id,
                from_column=m.from_column,
                to_column=m.to_column,
                moved_by=m.moved_by.value,
                timestamp=m.timestamp.isoformat(),
            )
            for m in board_adapter._movement_log
        ]

        return SimBoardHistoryResponse(
            board_id=board_id,
            movements=movements,
            total=len(movements),
        )

    return router
