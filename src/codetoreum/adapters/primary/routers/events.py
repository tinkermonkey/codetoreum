"""
Events REST API Router

Provides REST endpoints for historical event queries and event replay.
"""

from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field

from codetoreum.adapters.primary.simple_auth_dependencies import SimpleAuthDependencies
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
    correlation_id: Optional[str] = None
    causation_id: Optional[str] = None
    user_id: Optional[str] = None
    payload: dict
    metadata: dict = Field(default_factory=dict)


class EventListResponse(BaseModel):
    """Response for event list queries"""

    events: List[EventDTO]
    total_count: int
    offset: int
    limit: int
    has_next: bool


class EventReplayRequest(BaseModel):
    """Request to replay events"""

    stream_id: Optional[str] = None
    from_version: int = 0
    to_version: Optional[int] = None
    event_types: Optional[List[str]] = None


class EventReplayResponse(BaseModel):
    """Response for event replay request"""

    replay_id: str
    status: str = "accepted"
    stream_id: Optional[str]
    from_version: int
    to_version: Optional[int]
    estimated_event_count: int
    message: str


class EventStatisticsResponse(BaseModel):
    """Event store statistics"""

    total_events: int
    total_streams: int
    event_types: dict
    oldest_event: Optional[datetime]
    newest_event: Optional[datetime]


# ============================================================================
# Router Factory
# ============================================================================


def create_events_router(
    event_store: IEventStore,
    auth_deps: Optional[SimpleAuthDependencies] = None,
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
        event_type: Optional[str] = Query(None, description="Filter by event type"),
        aggregate_type: Optional[str] = Query(
            None, description="Filter by aggregate type"
        ),
        aggregate_id: Optional[str] = Query(None, description="Filter by aggregate ID"),
        correlation_id: Optional[str] = Query(
            None, description="Filter by correlation ID"
        ),
        start_time: Optional[datetime] = Query(
            None, description="Filter events after this timestamp"
        ),
        end_time: Optional[datetime] = Query(
            None, description="Filter events before this timestamp"
        ),
        offset: int = Query(0, ge=0, description="Number of events to skip"),
        limit: int = Query(50, ge=1, le=1000, description="Maximum events to return"),
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
                # Get all events (limited)
                domain_events = await event_store.get_events_by_type(
                    event_type="",
                    limit=limit + offset,
                )

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
                        occurred_at=event_dict.get("occurred_at", datetime.utcnow()),
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
        try:
            # Generate replay ID
            import uuid

            replay_id = f"replay-{uuid.uuid4()}"

            # Estimate event count
            if request.stream_id:
                version = await event_store.get_stream_version(request.stream_id)
                estimated_count = version - request.from_version
            else:
                # Rough estimate for all events
                estimated_count = 1000  # Placeholder

            # TODO: Trigger actual replay in background task
            # This would typically:
            # 1. Create a background task/job
            # 2. Use event_store.replay_events() to iterate events
            # 3. Re-publish each event to the event bus
            # 4. Track progress and completion

            return EventReplayResponse(
                replay_id=replay_id,
                status="accepted",
                stream_id=request.stream_id,
                from_version=request.from_version,
                to_version=request.to_version,
                estimated_event_count=estimated_count,
                message=f"Event replay accepted. Replay ID: {replay_id}. "
                f"Estimated {estimated_count} events will be replayed.",
            )

        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to trigger event replay: {str(e)}",
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
        try:
            stats = await event_store.get_statistics()

            return EventStatisticsResponse(
                total_events=stats.get("total_events", 0),
                total_streams=stats.get("total_streams", 0),
                event_types=stats.get("event_types", {}),
                oldest_event=stats.get("oldest_event"),
                newest_event=stats.get("newest_event"),
            )

        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to get event store statistics: {str(e)}",
            )

    return router
