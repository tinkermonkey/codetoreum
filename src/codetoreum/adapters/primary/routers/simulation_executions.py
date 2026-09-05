"""
Simulation Execution Status REST API Router

Provides simulation-only endpoints for querying execution status:
- GET /api/v2/sim/executions: List active and recently completed agent executions

This router combines data from:
1. IActiveWorkflowRunRegistry: Currently running executions
2. InMemoryEventStore: Recent completion events (WorkflowCompleted)

The endpoint supports optional filtering by status (active|completed|all).

This router is ONLY mounted in SimulationApplicationBootstrap, never in production.
"""

import logging
from collections.abc import Mapping
from datetime import datetime, timedelta
from typing import Literal

from fastapi import APIRouter, HTTPException, Query, status
from pydantic import BaseModel, Field

from codetoreum.adapters.testing.in_memory_active_workflow_run_registry import (
    InMemoryActiveWorkflowRunRegistry,
)
from codetoreum.adapters.testing.in_memory_event_store import InMemoryEventStore
from codetoreum.infrastructure.simulation.simulation_engine import SimulationEngine

logger = logging.getLogger(__name__)


# =========================================================================
# Request/Response DTOs
# =========================================================================


class ActiveExecution(BaseModel):
    """Representation of an active agent execution."""

    work_item_id: str = Field(..., description="Work item identifier")
    run_id: str = Field(..., description="Workflow run identifier")
    agent_id: str | None = Field(..., description="Agent identifier (if available)")
    stage_name: str = Field(..., description="Current pipeline stage")
    project_id: str = Field(..., description="Project identifier")
    status: str = Field(default="running", description="Execution status")
    started_at: datetime = Field(..., description="Time execution started (simulation time)")
    current_step: str | None = Field(..., description="Most recent event type for this run (current_step)")


class CompletedExecution(BaseModel):
    """Representation of a completed agent execution."""

    work_item_id: str = Field(..., description="Work item identifier")
    run_id: str = Field(..., description="Workflow run identifier")
    status: str = Field(default="completed", description="Execution status")
    completed_at: datetime = Field(..., description="Time execution completed (simulation time)")


class ExecutionStatusResponse(BaseModel):
    """Response containing active and recently completed executions."""

    snapshot_time: datetime = Field(..., description="Time of snapshot (simulation time)")
    active: list[ActiveExecution] = Field(default_factory=list, description="Currently active executions")
    recently_completed: list[CompletedExecution] = Field(
        default_factory=list, description="Recently completed executions (within 30 minutes)"
    )


# =========================================================================
# Router Factory
# =========================================================================


def create_simulation_executions_router(
    run_registry: InMemoryActiveWorkflowRunRegistry,
    event_store: InMemoryEventStore,
    clock: SimulationEngine,
) -> APIRouter:
    """
    Create the simulation executions status router.

    This router provides simulation-only endpoints for querying the status of agent
    executions. It combines data from the active run registry and event store.

    Args:
        run_registry: Active workflow run registry (tracks running executions)
        event_store: Event store (tracks completed executions via WorkflowCompleted events)
        clock: Simulation clock/engine for time queries

    Returns:
        APIRouter: Configured FastAPI router for execution status endpoints
    """
    router = APIRouter(prefix="/api/v2/sim", tags=["simulation-executions"])

    @router.get(
        "/executions",
        response_model=ExecutionStatusResponse,
        summary="Get execution status snapshot",
        description="Returns active and recently completed agent executions from the execution registry and event store.",
    )
    async def get_execution_status(
        status_filter: Literal["active", "completed", "all"] = Query(
            "all",
            alias="status",
            description="Filter by status: 'active', 'completed', or 'all'",
        ),
        minutes: int = Query(
            30,
            description="Minutes of history to include for completed executions",
            ge=1,
            le=1440,
        ),
    ) -> ExecutionStatusResponse:
        """
        Get execution status snapshot.

        Combines active executions from the run registry with recently completed
        executions from the event store.

        Query Parameters:
            status_filter: Filter results by status ('active', 'completed', or 'all'). Default: 'all'
            minutes: Number of minutes of history to include (1-1440). Default: 30

        Returns:
            ExecutionStatusResponse with active and recently_completed lists

        Raises:
            HTTPException(500): If an error occurs while reading execution status
        """
        try:
            now = clock.now()

            # =====================================================================
            # Query active executions from registry
            # =====================================================================
            active_executions: list[ActiveExecution] = []
            all_runs = await run_registry.get_all_runs()
            for work_item_id, run_info in all_runs:
                # Fetch events once per run and extract both current_step and agent execution info
                events = await event_store.get_events_by_correlation_id(str(run_info.run_id))
                current_step = _extract_current_step(events)
                agent_id, started_at = _extract_agent_execution_info(events)

                active = ActiveExecution(
                    work_item_id=work_item_id,
                    run_id=run_info.run_id,
                    agent_id=agent_id,  # Extracted from AgentExecutionStarted event
                    stage_name=run_info.stage_name,
                    project_id=run_info.project_id,
                    status="running",
                    started_at=started_at or now,  # Use actual start time from event, fallback to now
                    current_step=current_step,
                )
                active_executions.append(active)

            # =====================================================================
            # Query recently completed executions from event store
            # =====================================================================
            completed_executions: list[CompletedExecution] = []
            since = now - timedelta(minutes=minutes)

            # Get WorkflowCompleted events from the event store using public method.
            # Subtract one microsecond from since to preserve inclusive boundary behavior (>=)
            # because get_events_by_type uses strict > comparison internally.
            since_adjusted = since - timedelta(microseconds=1)
            workflow_completed_events = await event_store.get_events_by_type(
                "WorkflowCompletedEvent", since=since_adjusted
            )

            for event in workflow_completed_events:
                # Extract run_id from event if available
                run_id = _extract_run_id_from_event(event)
                work_item_id = _extract_work_item_id_from_event(event)

                completed = CompletedExecution(
                    work_item_id=work_item_id or "unknown",
                    run_id=run_id or "unknown",
                    status="completed",
                    completed_at=event.occurred_at,
                )
                completed_executions.append(completed)

            # =====================================================================
            # Apply status filter
            # =====================================================================
            if status_filter == "active":
                completed_executions = []
            elif status_filter == "completed":
                active_executions = []
            # else: status_filter == "all" - include both

            return ExecutionStatusResponse(
                snapshot_time=now,
                active=active_executions,
                recently_completed=completed_executions,
            )
        except Exception as e:
            logger.error(
                f"Error reading execution status: {e}",
                extra={"status_filter": status_filter, "minutes": minutes},
                exc_info=True,
            )
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Error reading execution status",
            ) from e

    return router


# =========================================================================
# Helper Functions
# =========================================================================


def _extract_agent_execution_info(events: list) -> tuple[str | None, datetime | None]:
    """
    Extract agent_id and started_at timestamp from AgentExecutionStarted event.

    Args:
        events: List of events for a given run (correlation_id)

    Returns:
        Tuple of (agent_id, started_at) where agent_id is the agent ID (or None),
        and started_at is the timestamp when execution started (or None)
    """
    # Search for AgentExecutionStarted event (first in the sequence for a run)
    for event in events:
        if event.event_type == "ExecutionStartedEvent":
            agent_id = getattr(event, "agent_id", None) or (
                getattr(event, "payload", {}).get("agent_id") if hasattr(event, "payload") else None
            )
            return agent_id, event.occurred_at

    return None, None


def _extract_current_step(events: list) -> str | None:
    """
    Extract the most recent event type for a given run.

    Args:
        events: List of events for a given run (correlation_id)

    Returns:
        Event type of the most recent event, or None if no events found
    """
    if not events:
        return None

    # Events should already be ordered, but sort by occurred_at descending to be safe
    sorted_events = sorted(events, key=lambda e: e.occurred_at, reverse=True)
    most_recent = sorted_events[0]
    # Return the event type as current_step
    return most_recent.event_type if hasattr(most_recent, "event_type") else None


def _extract_run_id_from_event(event: object) -> str | None:
    """Extract run_id from a WorkflowCompletedEvent."""
    # WorkflowCompletedEvent: workflow_id is the run identifier
    if hasattr(event, "workflow_id") and event.workflow_id:
        return str(event.workflow_id)

    # Fallback: correlation_id (event sourcing correlation)
    if hasattr(event, "correlation_id") and event.correlation_id:
        return str(event.correlation_id)

    # Legacy fallback: payload["run_id"]
    if hasattr(event, "payload"):
        payload = getattr(event, "payload", {})
        if isinstance(payload, Mapping) and "run_id" in payload:
            return payload["run_id"]

    return None


def _extract_work_item_id_from_event(event: object) -> str | None:
    """Extract work_item_id from a WorkflowCompletedEvent."""
    # WorkflowCompletedEvent: work_item_id is a direct field
    if hasattr(event, "work_item_id") and event.work_item_id:
        return event.work_item_id

    # Legacy fallback: payload["work_item_id"]
    if hasattr(event, "payload"):
        payload = getattr(event, "payload", {})
        if isinstance(payload, Mapping) and "work_item_id" in payload:
            return payload["work_item_id"]

    return None
