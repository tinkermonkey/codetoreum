"""
Server-Sent Events (SSE) Router for Real-Time Domain Event Streaming

Provides simulation-only endpoint for pushing domain events to connected clients in real time,
drawing events from the existing EventBus wildcard subscription mechanism.

Endpoint:
- GET /api/v2/sim/stream: SSE endpoint emitting domain events as they are published

Query parameters:
- ?event_type=<comma-separated types>: Filter by event type (e.g., WorkItemColumnChangedEvent)
- ?work_item_id=<id>: Filter by work item ID

This router is ONLY mounted in SimulationApplicationBootstrap, never in production.
"""

import asyncio
import json
import logging
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Query
from pydantic import BaseModel, Field
from starlette.responses import StreamingResponse

from codetoreum.domain.events import DomainEvent
from codetoreum.infrastructure.event_bus import EventBus
from codetoreum.infrastructure.simulation.simulation_engine import SimulationEngine

logger = logging.getLogger(__name__)

# Configuration constants
SSE_KEEPALIVE_INTERVAL_SECONDS = 15
SSE_QUEUE_MAXSIZE = 1000
SSE_MAX_CONCURRENT_CONNECTIONS = 50


# =========================================================================
# Request/Response DTOs
# =========================================================================


class SSEEventPayload(BaseModel):
    """SSE event payload sent to connected clients."""

    event_type: str = Field(..., description="Type of domain event")
    event_id: str = Field(..., description="Unique event ID")
    timestamp: datetime = Field(..., description="Wall-clock UTC timestamp when event occurred")
    simulation_time: datetime = Field(..., description="Simulation time from engine.now()")
    work_item_id: str | None = Field(None, description="Work item ID if applicable")
    agent_id: str | None = Field(None, description="Agent ID if applicable")
    details: dict[str, Any] = Field(default_factory=dict, description="Event-specific payload details")


# =========================================================================
# SSE Frame Formatting
# =========================================================================


def format_sse_frame(event_type: str, event_id: str, data: dict[str, Any]) -> str:
    """
    Format an SSE frame according to standard SSE protocol.

    Args:
        event_type: Type of the event
        event_id: Unique event ID
        data: Event data as dictionary

    Returns:
        Formatted SSE frame string (including trailing double-newline)
    """
    frame = f"event: {event_type}\n"
    frame += f"id: {event_id}\n"
    # Use ensure_ascii=False for proper unicode support (emoji, international characters)
    frame += f"data: {json.dumps(data, ensure_ascii=False)}\n\n"
    return frame


def format_keepalive_comment() -> str:
    """Format a keepalive comment to prevent proxy timeouts."""
    return ":keepalive\n\n"


# =========================================================================
# Event Filtering
# =========================================================================


def event_matches_filters(
    event: DomainEvent,
    event_types: list[str] | None,
    work_item_id: str | None,
) -> bool:
    """
    Check if an event matches the specified filters.

    Filters are applied before enqueueing to avoid unnecessary serialization.

    Args:
        event: Domain event to check
        event_types: List of event types to accept (None = accept all)
        work_item_id: Work item ID to filter on (None = accept all)

    Returns:
        True if event matches all specified filters
    """
    # Check event type filter
    if event_types is not None and event.event_type not in event_types:
        return False

    # Check work_item_id filter
    if work_item_id is not None:
        # Extract work_item_id from payload
        event_work_item_id = event.payload.get("work_item_id")
        if event_work_item_id != work_item_id:
            return False

    return True


# =========================================================================
# Router Factory
# =========================================================================


def create_simulation_stream_router(
    event_bus: EventBus,
    clock: SimulationEngine,
) -> APIRouter:
    """
    Create the SSE stream router.

    This router provides simulation-only endpoints for real-time event streaming.
    It takes concrete simulation types (not port interfaces) because this is
    simulation infrastructure, not production code.

    Connection state is scoped to the router instance to support multiple
    router instances (e.g., in tests or when bootstrap is recreated).

    Args:
        event_bus: EventBus for subscribing to domain events
        clock: SimulationEngine for timestamp generation

    Returns:
        Configured APIRouter
    """
    # Router instance state - scoped to this router, not global
    connection_state = {"count": 0, "lock": asyncio.Lock()}

    router = APIRouter(prefix="/api/v2/sim", tags=["simulation-stream"])

    @router.get("/stream", response_class=StreamingResponse)
    async def stream_events(
        event_type: str | None = Query(
            None,
            description="Comma-separated list of event types to stream (e.g., WorkItemColumnChangedEvent,WorkflowStartedEvent)",
        ),
        work_item_id: str | None = Query(
            None,
            description="Filter events by work item ID",
        ),
    ):
        """
        Stream domain events in real time via Server-Sent Events.

        Uses Starlette's StreamingResponse with text/event-stream media type.
        Each event is emitted as it is published to the event bus.

        Query parameters:
        - event_type: Comma-separated list of event types to filter (optional)
        - work_item_id: Filter by work item ID (optional)

        Returns:
            StreamingResponse with text/event-stream media type
        """
        # Parse comma-separated event types
        event_types = None
        if event_type:
            event_types = [et.strip() for et in event_type.split(",") if et.strip()]

        # Create per-client queue for event buffering
        queue: asyncio.Queue[DomainEvent | None] = asyncio.Queue(maxsize=SSE_QUEUE_MAXSIZE)

        # Define callback to enqueue events matching filters
        async def event_callback(event: DomainEvent) -> None:
            """
            Callback invoked when event is published.

            Filtering applied here before enqueueing to avoid unnecessary serialization.
            """
            if not event_matches_filters(event, event_types, work_item_id):
                return

            try:
                # Try to put event without blocking
                queue.put_nowait(event)
            except asyncio.QueueFull:
                # Drop oldest event and enqueue new one
                try:
                    queue.get_nowait()
                except asyncio.QueueEmpty:
                    pass

                try:
                    queue.put_nowait(event)
                except asyncio.QueueFull:
                    # Log warning but continue - don't break the stream
                    logger.warning(
                        "SSE queue full, dropping event",
                        extra={
                            "event_type": event.event_type,
                            "event_id": str(event.event_id),
                        },
                    )

        # Create async generator for streaming response
        async def event_generator():
            """
            Async generator yielding SSE frames.

            Handles:
            - Event streaming from queue
            - Keepalive comments every 15 seconds during idle periods
            - Cleanup on client disconnect (via GeneratorExit from aclose())
            """
            # Check connection limit
            async with connection_state["lock"]:
                if connection_state["count"] >= SSE_MAX_CONCURRENT_CONNECTIONS:
                    # Send error and close
                    yield f'event: error\ndata: {{"error": "Max concurrent connections ({SSE_MAX_CONCURRENT_CONNECTIONS}) reached"}}\n\n'
                    return

                connection_state["count"] += 1

            logger.info(
                "SSE client connected",
                extra={
                    "event_type_filter": event_types,
                    "work_item_id_filter": work_item_id,
                    "active_connections": connection_state["count"],
                },
            )

            # Subscribe to event bus (wildcard - receive all events)
            event_bus.subscribe(None, event_callback)

            try:
                while True:
                    try:
                        # Wait for event with keepalive timeout
                        event = await asyncio.wait_for(
                            queue.get(),
                            timeout=SSE_KEEPALIVE_INTERVAL_SECONDS,
                        )

                        # Serialize event to SSE payload, excluding work_item_id and agent_id from details
                        # to avoid redundancy (they appear as top-level fields)
                        details_dict = dict(event.payload)
                        details_dict.pop("work_item_id", None)
                        details_dict.pop("agent_id", None)

                        payload = SSEEventPayload(
                            event_type=event.event_type,
                            event_id=str(event.event_id),
                            timestamp=event.occurred_at,
                            simulation_time=clock.now(),
                            work_item_id=event.payload.get("work_item_id"),
                            agent_id=event.payload.get("agent_id"),
                            details=details_dict,
                        )

                        # Yield SSE frame
                        yield format_sse_frame(
                            payload.event_type,
                            payload.event_id,
                            payload.model_dump(mode="json", exclude_none=False),
                        )

                    except TimeoutError:
                        # No event received within timeout - send keepalive
                        yield format_keepalive_comment()

            except asyncio.CancelledError:
                # Client disconnected (caught but logged separately for diagnostics)
                logger.debug(
                    "SSE client disconnected via CancelledError",
                    extra={
                        "event_type_filter": event_types,
                        "work_item_id_filter": work_item_id,
                    },
                )
                raise

            finally:
                # Unsubscribe from event bus
                event_bus.unsubscribe(None, event_callback)

                # Decrement connection count
                async with connection_state["lock"]:
                    connection_state["count"] -= 1

                logger.info(
                    "SSE cleanup complete",
                    extra={
                        "active_connections": connection_state["count"],
                    },
                )

        return StreamingResponse(
            event_generator(),
            media_type="text/event-stream",
        )

    return router
