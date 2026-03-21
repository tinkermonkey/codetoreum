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
from datetime import datetime, timedelta
from typing import Literal

from fastapi import APIRouter, Query
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
        """
        now = clock.now()

        # =====================================================================
        # Query active executions from registry
        # =====================================================================
        active_executions: list[ActiveExecution] = []
        for work_item_id, run_info in run_registry._runs.items():
            # Find most recent event for this run to determine current_step and get execution start info
            current_step = _get_current_step(event_store, run_info.run_id)
            agent_id, started_at = _get_agent_execution_info(event_store, run_info.run_id)

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

        # Get WorkflowCompleted events from the event store
        workflow_completed_events = event_store._events_by_type.get("WorkflowCompleted", [])

        for event in workflow_completed_events:
            # Only include events within the time window
            if event.occurred_at >= since:
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

    return router


# =========================================================================
# Helper Functions
# =========================================================================


def _get_agent_execution_info(event_store: InMemoryEventStore, run_id: str) -> tuple[str | None, datetime | None]:
    """
    Extract agent_id and started_at timestamp from AgentExecutionStarted event.

    Args:
        event_store: Event store to query
        run_id: Run identifier to look up (used as correlation_id)

    Returns:
        Tuple of (agent_id, started_at) where agent_id is the agent ID (or None),
        and started_at is the timestamp when execution started (or None)
    """
    events = event_store._events_by_correlation.get(str(run_id), [])

    # Search for AgentExecutionStarted event (first in the sequence for a run)
    for event in events:
        if event.event_type == "AgentExecutionStarted":
            agent_id = event.payload.get("agent_id")
            return agent_id, event.occurred_at

    return None, None


def _get_current_step(event_store: InMemoryEventStore, run_id: str) -> str | None:
    """
    Extract the most recent event type for a given run (correlation_id).

    Args:
        event_store: Event store to query
        run_id: Run identifier to look up (used as correlation_id)

    Returns:
        Event type of the most recent event, or None if no events found
    """
    run_id_str = str(run_id)
    events = event_store._events_by_correlation.get(run_id_str, [])

    if not events:
        return None

    # Events should already be ordered, but sort by occurred_at descending to be safe
    sorted_events = sorted(events, key=lambda e: e.occurred_at, reverse=True)
    most_recent = sorted_events[0]
    # Return the event type as current_step
    return most_recent.event_type if hasattr(most_recent, "event_type") else None


def _extract_run_id_from_event(event: object) -> str | None:
    """
    Extract run_id from a WorkflowCompleted event.

    WorkflowCompleted events have a correlation_id or aggregate_id that may correspond
    to the run. We try multiple paths to find the run identifier.

    Args:
        event: Domain event object

    Returns:
        Run ID if found, None otherwise
    """
    # Try correlation_id first (used for event sourcing)
    if hasattr(event, "correlation_id"):
        correlation_id = event.correlation_id
        if correlation_id:
            return str(correlation_id)

    # Try aggregate_id (fallback)
    if hasattr(event, "aggregate_id"):
        aggregate_id = event.aggregate_id
        if aggregate_id:
            return str(aggregate_id)

    # Try payload (for newer event models)
    if hasattr(event, "payload"):
        payload = getattr(event, "payload", {})
        if isinstance(payload, dict) and "run_id" in payload:
            return payload["run_id"]

    return None


def _extract_work_item_id_from_event(event: object) -> str | None:
    """
    Extract work_item_id from a WorkflowCompleted event.

    Args:
        event: Domain event object

    Returns:
        Work item ID if found, None otherwise
    """
    # Try payload first (common location for context data)
    if hasattr(event, "payload"):
        payload = getattr(event, "payload", {})
        if isinstance(payload, dict):
            if "work_item_id" in payload:
                return payload["work_item_id"]

    # Try aggregate_id (if it encodes work item ID)
    if hasattr(event, "aggregate_id"):
        aggregate_id = event.aggregate_id
        if aggregate_id:
            return str(aggregate_id)

    return None
