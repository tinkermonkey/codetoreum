"""
Simulation Board State Snapshot REST API Router

Provides a simulation-only endpoint for retrieving the current state of a board:
- GET /api/v2/sim/boards/{board_id}/state: Returns column-to-work-items mapping with enrichment

This router reads from:
1. MockBoardAdapter._boards, _item_positions, _item_column_entries (board state)
2. IActiveWorkflowRunRegistry._runs (agent assignments and execution status)
3. InMemoryTicketAdapter (work item titles)

The endpoint returns a snapshot of the board state at request time (read-only), reflecting:
- Current column structure and work item ordering
- Time each work item entered its current column
- Assigned agent and execution stage (if active run exists)

Thread safety:
- All reads from board adapter state are performed under board_adapter._lock
- Concurrent title lookups from ticket adapter are performed after lock release

This router is ONLY mounted in SimulationApplicationBootstrap, never in production.
"""

import asyncio
import logging
from datetime import datetime

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field

from codetoreum.adapters.testing.in_memory_active_workflow_run_registry import (
    InMemoryActiveWorkflowRunRegistry,
)
from codetoreum.adapters.testing.in_memory_ticket_adapter import InMemoryTicketAdapter
from codetoreum.adapters.testing.mock_board_adapter import MockBoardAdapter
from codetoreum.infrastructure.simulation.simulation_engine import SimulationEngine

logger = logging.getLogger(__name__)


# =========================================================================
# Request/Response DTOs
# =========================================================================


class WorkItemState(BaseModel):
    """State of a work item in a column."""

    work_item_id: str = Field(..., description="Unique identifier of the work item")
    title: str | None = Field(..., description="Work item title (None if not found in ticket adapter)")
    position: int = Field(..., description="Position of the item in the column (0-indexed)")
    entered_column_at: datetime = Field(..., description="Timestamp when the item entered this column (UTC)")
    time_in_column_seconds: float = Field(
        ...,
        description="Number of seconds the item has been in the current column",
        ge=0,
    )
    assigned_agent: str | None = Field(..., description="Name of the assigned agent (None if no active run)")
    execution_status: str | None = Field(..., description="Current execution stage/status (None if no active run)")


class ColumnState(BaseModel):
    """State of a board column."""

    name: str = Field(..., description="Column name")
    items: list[WorkItemState] = Field(default_factory=list, description="Work items in this column")


class BoardStateResponse(BaseModel):
    """Complete board state snapshot response."""

    board_id: str = Field(..., description="Board identifier")
    board_name: str | None = Field(..., description="Human-readable board name (None if not found)")
    snapshot_time: datetime = Field(..., description="Timestamp of the snapshot (from simulation clock)")
    columns: list[ColumnState] = Field(..., description="All columns in the board, ordered by position")


# =========================================================================
# Router Factory
# =========================================================================


def create_simulation_board_state_router(
    board_adapter: MockBoardAdapter,
    run_registry: InMemoryActiveWorkflowRunRegistry,
    ticket_adapter: InMemoryTicketAdapter,
    clock: SimulationEngine,
) -> APIRouter:
    """
    Create the simulation board state snapshot router.

    This router provides a simulation-only endpoint for retrieving the current state
    of a board without triggering mutations. It uses direct adapter access (not port
    interfaces) because this is simulation infrastructure.

    Args:
        board_adapter: MockBoardAdapter instance containing board state
        run_registry: InMemoryActiveWorkflowRunRegistry for agent assignments
        ticket_adapter: InMemoryTicketAdapter for work item titles
        clock: SimulationEngine for getting current snapshot timestamp

    Returns:
        Configured APIRouter for board state snapshots
    """
    router = APIRouter(
        prefix="/api/v2/sim",
        tags=["simulation-board-state"],
    )

    # =====================================================================
    # Board State Snapshot Endpoint
    # =====================================================================

    @router.get("/boards/{board_id}/state", response_model=BoardStateResponse, status_code=status.HTTP_200_OK)
    async def get_board_state(board_id: str) -> BoardStateResponse:
        """
        Get current state of a board with column-to-work-items mapping.

        This endpoint returns a read-only snapshot of the board state at request time,
        including:
        - Column structure and ordering
        - Work items in each column with positions
        - Time each work item entered its current column
        - Agent assignments and execution status from active workflow runs
        - Work item titles (enriched from ticket adapter)

        The snapshot is atomic with respect to board state reads (performed under lock),
        but work item title lookups are concurrent (performed after lock release) for
        performance.

        Args:
            board_id: The board to snapshot

        Returns:
            Complete board state with column and work item details

        Raises:
            HTTPException(404): If board_id does not exist in adapter state
        """
        snapshot_time = clock.now()

        # Acquire lock and snapshot board state
        # ===================================================================
        try:
            async with board_adapter._lock:
                # Verify board exists
                if board_id not in board_adapter._board_project_map:
                    raise HTTPException(
                        status_code=status.HTTP_404_NOT_FOUND,
                        detail=f"Board not found: {board_id}",
                    )

                # Get the project ID for this board
                project_id = board_adapter._board_project_map[board_id]
                key = f"{project_id}:{board_id}"

                # Get the board object (contains column definitions)
                board = board_adapter._boards.get(key)
                if not board:
                    raise HTTPException(
                        status_code=status.HTTP_404_NOT_FOUND,
                        detail=f"Board not found: {board_id}",
                    )

                # Extract board metadata
                board_name = board.name
                columns_ordered = sorted(board.columns, key=lambda c: c.position)

                # Build column structure with work items
                columns_data: list[dict] = []

                for column in columns_ordered:
                    column_items: list[dict] = []

                    # Find all items in this column
                    for item_id, (pos_board_id, pos_column_name, position) in board_adapter._item_positions.items():
                        if pos_board_id == board_id and pos_column_name == column.name:
                            entered_at = board_adapter._item_column_entries.get(item_id)

                            # Handle missing timestamp (use snapshot_time as fallback, but shouldn't happen)
                            if entered_at is None:
                                entered_at = snapshot_time
                                logger.warning(
                                    f"Work item {item_id} has no entered_column_at timestamp; using snapshot time",
                                    extra={"item_id": item_id, "column": column.name},
                                )

                            # Compute time in column
                            time_delta = snapshot_time - entered_at
                            time_in_column = max(0.0, time_delta.total_seconds())

                            # Look up active run (stage/agent info)
                            active_run = run_registry._runs.get(item_id)
                            stage_name = active_run.stage_name if active_run else None
                            # Agent name is derived from stage_name or we could get run_id
                            agent_name = active_run.run_id if active_run else None

                            column_items.append(
                                {
                                    "work_item_id": item_id,
                                    "position": position,
                                    "entered_column_at": entered_at,
                                    "time_in_column_seconds": time_in_column,
                                    "assigned_agent": agent_name,
                                    "execution_status": stage_name,
                                }
                            )

                    # Sort items by position within column
                    column_items.sort(key=lambda x: x["position"])

                    columns_data.append(
                        {
                            "name": column.name,
                            "position": column.position,
                            "items": column_items,
                        }
                    )

        except HTTPException:
            raise
        except Exception as e:
            logger.error(
                f"Error reading board state: {e}",
                extra={"board_id": board_id},
                exc_info=True,
            )
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Error reading board state",
            ) from e

        # Fetch work item titles concurrently (outside lock)
        # ===================================================================
        # Collect all work item IDs that need titles
        item_ids_needing_titles = set()
        for column_data in columns_data:
            for item_data in column_data["items"]:
                item_ids_needing_titles.add(item_data["work_item_id"])

        # Batch fetch titles from ticket adapter
        title_tasks = [_get_work_item_title(ticket_adapter, item_id) for item_id in item_ids_needing_titles]

        if title_tasks:
            titles_list = await asyncio.gather(*title_tasks, return_exceptions=True)
            titles_dict = {}
            for item_id, title in zip(item_ids_needing_titles, titles_list, strict=False):
                if isinstance(title, Exception):
                    logger.error(
                        f"Failed to fetch title for work item {item_id}: {title}",
                        extra={"item_id": item_id},
                        exc_info=title,
                    )
                else:
                    titles_dict[item_id] = title
        else:
            titles_dict = {}

        # Assemble final response with titles
        # ===================================================================
        columns_response = []
        for column_data in columns_data:
            items_response = []
            for item_data in column_data["items"]:
                title = titles_dict.get(item_data["work_item_id"])
                items_response.append(
                    WorkItemState(
                        work_item_id=item_data["work_item_id"],
                        title=title,
                        position=item_data["position"],
                        entered_column_at=item_data["entered_column_at"],
                        time_in_column_seconds=item_data["time_in_column_seconds"],
                        assigned_agent=item_data["assigned_agent"],
                        execution_status=item_data["execution_status"],
                    )
                )

            columns_response.append(
                ColumnState(
                    name=column_data["name"],
                    items=items_response,
                )
            )

        return BoardStateResponse(
            board_id=board_id,
            board_name=board_name,
            snapshot_time=snapshot_time,
            columns=columns_response,
        )

    return router


# =========================================================================
# Helper Functions
# =========================================================================


async def _get_work_item_title(ticket_adapter: InMemoryTicketAdapter, item_id: str) -> str | None:
    """
    Safely fetch work item title from ticket adapter.

    Args:
        ticket_adapter: InMemoryTicketAdapter instance
        item_id: Work item identifier

    Returns:
        Work item title, or None if not found or error occurs
    """
    try:
        work_item = await ticket_adapter.get_work_item(item_id)
        return work_item.title
    except Exception as e:
        logger.debug(
            f"Could not fetch title for work item {item_id}: {e}",
            extra={"item_id": item_id},
        )
        return None
