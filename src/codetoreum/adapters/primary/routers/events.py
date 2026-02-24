"""
Events REST API Router

Provides REST endpoints for historical event queries and event replay.
"""

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field

from codetoreum.adapters.primary.simple_auth_dependencies import SimpleAuthDependencies
from codetoreum.config import (
    DEFAULT_OFFSET,
    EVENTS_DEFAULT_PAGE_SIZE,
    EVENTS_MAX_PAGE_SIZE,
)
from codetoreum.ports.output.event_store import IEventStore

# ============================================================================
# DTOs (Data Transfer Objects)
# ============================================================================


class EventDTO(BaseModel):
    """Event data transfer object"""

    event_id: str
    event_type: str
    event_version: int
    aggregate_id: str
    aggregate_type: str
    occurred_at: datetime
    correlation_id: str | None = None
    causation_id: str | None = None
    user_id: str | None = None
    payload: dict
    metadata: dict = Field(default_factory=dict)


class EventListResponse(BaseModel):
    """Response for event list queries"""

    events: list[EventDTO]
    total_count: int
    offset: int
    limit: int
    has_next: bool


class EventReplayRequest(BaseModel):
    """Request to replay events"""

    stream_id: str | None = None
    from_version: int = 0
    to_version: int | None = None
    event_types: list[str] | None = None


class EventReplayResponse(BaseModel):
    """Response for event replay request"""

    replay_id: str
    status: str = "accepted"
    stream_id: str | None
    from_version: int
    to_version: int | None
    estimated_event_count: int
    message: str


class EventStatisticsResponse(BaseModel):
    """Event store statistics"""

    total_events: int
    total_streams: int
    event_types: dict
    oldest_event: datetime | None
    newest_event: datetime | None


# ============================================================================
# Router Factory
# ============================================================================


def create_events_router(
    event_store: IEventStore,
    auth_deps: SimpleAuthDependencies | None = None,
) -> APIRouter:
    """
    Create events REST API router.

    Args:
        event_store: Event store port for querying events
        auth_deps: Authentication dependencies (optional for testing)

    Returns:
        Configured APIRouter
    """
    router = APIRouter(
        prefix="/api/v2/events",
        tags=["events"],
        dependencies=[Depends(auth_deps.require_auth)] if auth_deps else [],
    )

    @router.get(
        "",
        response_model=EventListResponse,
        summary="Get historical events",
        description="Query historical events with pagination and filtering",
    )
    async def get_events(
        event_type: str | None = Query(None, description="Filter by event type"),
        aggregate_type: str | None = Query(
            None, description="Filter by aggregate type"
        ),
        aggregate_id: str | None = Query(None, description="Filter by aggregate ID"),
        correlation_id: str | None = Query(
            None, description="Filter by correlation ID"
        ),
        start_time: datetime | None = Query(
            None, description="Filter events after this timestamp"
        ),
        end_time: datetime | None = Query(
            None, description="Filter events before this timestamp"
        ),
        offset: int = Query(DEFAULT_OFFSET, ge=0, description="Number of events to skip"),
        limit: int = Query(EVENTS_DEFAULT_PAGE_SIZE, ge=1, le=EVENTS_MAX_PAGE_SIZE, description=f"Maximum events to return (max {EVENTS_MAX_PAGE_SIZE})"),
    ) -> EventListResponse:
        """
        Get historical events with filtering and pagination.

        Supports filtering by:
        - Event type (e.g., "ExecutionStarted", "WorkflowCompleted")
        - Aggregate type (e.g., "AgentExecution", "Workflow")
        - Aggregate ID
        - Correlation ID (to trace related events)
        - Time range (start_time and/or end_time)

        Events are returned in chronological order (oldest first).
        """
        try:
            events = []

            # Query by correlation ID if provided
            if correlation_id:
                domain_events = await event_store.get_events_by_correlation_id(
                    correlation_id
                )
            # Query by event type if provided
            elif event_type:
                domain_events = await event_store.get_events_by_type(
                    event_type=event_type,
                    since=start_time,
                    limit=limit + offset,
                )
            # Query by aggregate ID (stream)
            elif aggregate_id:
                domain_events = await event_store.get_events(
                    stream_id=aggregate_id,
                    from_version=0,
                )
            # Query by time range
            elif start_time:
                domain_events = await event_store.get_events_since(
                    since=start_time,
                    stream_id=aggregate_id,
                )
            else:
                # Get all events - need to get all stream IDs and iterate
                all_stream_ids = await event_store.get_all_stream_ids()
                domain_events = []
                for stream_id in all_stream_ids:
                    stream_events = await event_store.get_events(stream_id=stream_id, from_version=0)
                    domain_events.extend(stream_events)

                # Sort by timestamp
                domain_events.sort(key=lambda e: e.occurred_at if hasattr(e, 'occurred_at') else e.timestamp)

            # Filter by aggregate type if specified
            if aggregate_type:
                domain_events = [
                    e
                    for e in domain_events
                    if getattr(e, "aggregate_type", None) == aggregate_type
                ]

            # Filter by time range
            if end_time:
                domain_events = [
                    e
                    for e in domain_events
                    if getattr(e, "occurred_at", None) <= end_time
                ]

            # Apply pagination
            total_count = len(domain_events)
            domain_events = domain_events[offset : offset + limit]

            # Convert to DTOs
            for event in domain_events:
                event_dict = (
                    event.to_dict() if hasattr(event, "to_dict") else event.__dict__
                )
                events.append(
                    EventDTO(
                        event_id=str(event_dict.get("event_id", "")),
                        event_type=event_dict.get("event_type", type(event).__name__),
                        event_version=event_dict.get("event_version", 1),
                        aggregate_id=event_dict.get("aggregate_id", ""),
                        aggregate_type=event_dict.get("aggregate_type", ""),
                        occurred_at=event_dict.get("occurred_at", datetime.now(timezone.utc)),
                        correlation_id=str(event_dict.get("correlation_id"))
                        if event_dict.get("correlation_id")
                        else None,
                        causation_id=str(event_dict.get("causation_id"))
                        if event_dict.get("causation_id")
                        else None,
                        user_id=event_dict.get("user_id"),
                        payload=event_dict.get("payload", {}),
                        metadata=event_dict.get("metadata", {}),
                    )
                )

            return EventListResponse(
                events=events,
                total_count=total_count,
                offset=offset,
                limit=limit,
                has_next=(offset + limit) < total_count,
            )

        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to query events: {str(e)}",
            )

    @router.post(
        "/replay",
        response_model=EventReplayResponse,
        status_code=status.HTTP_202_ACCEPTED,
        summary="Replay events",
        description="Trigger event replay for debugging and recovery",
    )
    async def replay_events(
        request: EventReplayRequest,
    ) -> EventReplayResponse:
        """
        Trigger event replay for a stream or all events.

        Event replay re-publishes historical events to the event bus,
        allowing you to:
        - Reconstruct aggregate state from events
        - Debug workflow issues
        - Replay events after fixing bugs in event handlers

        **Note**: This is an async operation. The replay happens in the background.
        """
        # Event replay is not yet implemented
        raise HTTPException(
            status_code=status.HTTP_501_NOT_IMPLEMENTED,
            detail="Event replay not yet implemented",
        )

    @router.get(
        "/statistics",
        response_model=EventStatisticsResponse,
        summary="Get event store statistics",
        description="Get statistics about the event store",
    )
    async def get_statistics() -> EventStatisticsResponse:
        """
        Get event store statistics.

        Returns aggregate statistics about:
        - Total number of events
        - Total number of streams (aggregates)
        - Event type distribution
        - Oldest and newest event timestamps
        """
        # Statistics method not yet defined in IEventStore interface
        raise HTTPException(
            status_code=status.HTTP_501_NOT_IMPLEMENTED,
            detail="Event statistics not yet implemented",
        )

    return router
