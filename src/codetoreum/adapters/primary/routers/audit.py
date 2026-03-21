"""
Audit Events REST API Router

Provides RESTful endpoints for querying system-wide audit events.
"""

import logging
from datetime import datetime
from typing import TYPE_CHECKING, Any

from fastapi import APIRouter, Depends, HTTPException, Path, Query
from fastapi import status as http_status

from codetoreum.adapters.primary.audit_dtos import (
    AuditEventsListResponse,
    CausalChainEvent,
    CausalChainResponse,
)
from codetoreum.adapters.primary.simple_auth_dependencies import SimpleAuthDependencies
from codetoreum.config import DEFAULT_OFFSET
from codetoreum.config.defaults import AUDIT_EVENTS_MAX_PAGE_SIZE
from codetoreum.ports.input.audit_query import (
    AuditEventFilters,
    AuditEventPaginationParams,
    IAuditQueryPort,
)

if TYPE_CHECKING:
    from codetoreum.adapters.testing.in_memory_event_store import InMemoryEventStore
    from codetoreum.infrastructure.simulation.causal_link_registry import (
        CausalLinkRegistry,
    )
    from codetoreum.infrastructure.simulation.simulation_clock import SimulationClock

logger = logging.getLogger(__name__)


def create_audit_router(
    query_port: IAuditQueryPort,
    auth_deps: SimpleAuthDependencies | None = None,
    event_store: "InMemoryEventStore | None" = None,
    causal_link_registry: "CausalLinkRegistry | None" = None,
    simulation_clock: "SimulationClock | None" = None,
) -> APIRouter:
    """
    Create the audit events REST API router.

    Args:
        query_port: Audit query input port
        auth_deps: Optional authentication dependencies
        event_store: Optional InMemoryEventStore for causal chain traversal (simulation-only)
        causal_link_registry: Optional CausalLinkRegistry for causal dependency metadata (simulation-only)
        simulation_clock: Optional SimulationClock for time-aware event timestamps (simulation-only)

    Returns:
        Configured APIRouter for audit events
    """
    # Create router with authentication dependency if provided
    router_kwargs = {
        "prefix": "/api/v2/audit",
        "tags": ["audit"],
    }
    if auth_deps:
        router_kwargs["dependencies"] = [Depends(auth_deps.require_auth)]

    router = APIRouter(**router_kwargs)

    # ========================================================================
    # List Audit Events
    # ========================================================================

    @router.get(
        "/events",
        response_model=AuditEventsListResponse,
        summary="List audit events with filtering and pagination",
        response_description="List of audit events",
    )
    async def list_audit_events(
        eventType: str | None = Query(
            None,
            description="Filter by event type (single value or comma-separated for multiple)",
            alias="eventType",
        ),
        resourceType: str | None = Query(
            None,
            description="Filter by resource type",
            alias="resourceType",
        ),
        resourceId: str | None = Query(
            None,
            description="Filter by resource ID",
            alias="resourceId",
        ),
        userId: str | None = Query(
            None,
            description="Filter by user ID",
            alias="userId",
        ),
        action: str | None = Query(
            None,
            description="Filter by action (create, update, delete, etc.)",
        ),
        success: bool | None = Query(
            None,
            description="Filter by success status (true or false)",
        ),
        startTime: datetime | None = Query(
            None,
            description="Filter events after this ISO timestamp",
            alias="startTime",
        ),
        endTime: datetime | None = Query(
            None,
            description="Filter events before this ISO timestamp",
            alias="endTime",
        ),
        since: datetime | None = Query(
            None,
            description="Filter events after this ISO timestamp (alias for startTime)",
        ),
        workItemId: str | None = Query(
            None,
            description="Filter events associated with a specific work item ID",
            alias="workItemId",
        ),
        offset: int = Query(DEFAULT_OFFSET, ge=0, description="Offset for pagination"),
        limit: int = Query(
            20,
            ge=1,
            le=AUDIT_EVENTS_MAX_PAGE_SIZE,
            description=f"Limit for pagination (max {AUDIT_EVENTS_MAX_PAGE_SIZE})",
        ),
    ) -> AuditEventsListResponse:
        """
        List audit events with optional filtering and pagination.

        **Query Parameters:**
        - eventType: Filter by event type (e.g., agent_created, config_updated)
        - resourceType: Filter by resource type (e.g., agent, workflow, config)
        - resourceId: Filter by resource ID
        - userId: Filter by user ID
        - action: Filter by action (create, update, delete)
        - success: Filter by success status
        - startTime: Filter events after this time (ISO timestamp)
        - endTime: Filter events before this time (ISO timestamp)
        - offset: Pagination offset (default: 0)
        - limit: Pagination limit (default: 20, max: 200)

        **Returns:**
        - 200 OK: List of audit events with pagination metadata
        - 400 Bad Request: Invalid filter parameters
        - 401 Unauthorized: Authentication required

        **Examples:**
        - List all events: `GET /api/v2/audit/events`
        - Filter by type: `GET /api/v2/audit/events?eventType=agent_created`
        - Filter by resource: `GET /api/v2/audit/events?resourceType=workflow&resourceId=wf-123`
        - Filter by time range: `GET /api/v2/audit/events?startTime=2026-02-20T00:00:00Z&endTime=2026-02-21T00:00:00Z`
        - Filter by since: `GET /api/v2/audit/events?since=2026-02-20T00:00:00Z`
        - Filter by work item: `GET /api/v2/audit/events?workItemId=WI-123`
        - Paginate: `GET /api/v2/audit/events?offset=20&limit=20`

        **Note:** The `since` and `startTime` parameters are aliases. If both are provided, a 400 Bad Request is returned.
        """
        try:
            # Reject if both 'since' and 'startTime' are provided
            if since is not None and startTime is not None:
                raise HTTPException(
                    status_code=http_status.HTTP_400_BAD_REQUEST,
                    detail="Cannot provide both 'since' and 'startTime' parameters. Use 'since' as the preferred alias for 'startTime'.",
                )

            # Use 'since' as alias for 'startTime' if provided
            effective_start_time = since if since is not None else startTime

            # Build filters
            filters = None
            if any(
                [
                    eventType,
                    resourceType,
                    resourceId,
                    userId,
                    action,
                    success is not None,
                    effective_start_time,
                    endTime,
                    workItemId,
                ]
            ):
                filters = AuditEventFilters(
                    event_type=eventType,
                    resource_type=resourceType,
                    resource_id=resourceId,
                    user_id=userId,
                    action=action,
                    success=success,
                    start_time=effective_start_time,
                    end_time=endTime,
                    work_item_id=workItemId,
                )

            # Build pagination
            pagination = AuditEventPaginationParams(
                offset=offset,
                limit=limit,
            )

            # Execute query via port
            result = await query_port.query_audit_events(filters, pagination)

            # Convert to response DTO
            return AuditEventsListResponse(
                events=[
                    {
                        "id": event.id,
                        "timestamp": event.timestamp,
                        "eventType": event.event_type,
                        "resourceType": event.resource_type,
                        "resourceId": event.resource_id,
                        "action": event.action,
                        "userId": event.user_id,
                        "correlationId": event.correlation_id,
                        "success": event.success,
                        "errorMessage": event.error_message,
                        "metadata": event.metadata,
                    }
                    for event in result.events
                ],
                totalEventCount=result.total_count,
                offset=result.offset,
                limit=result.limit,
                hasNext=result.has_next,
            )

        except HTTPException:
            raise
        except Exception as e:
            logger.error(
                "Unexpected error listing audit events",
                exc_info=True,
                extra={"error": str(e)},
            )
            raise HTTPException(
                status_code=http_status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Internal server error while listing audit events",
            )

    # ========================================================================
    # Causal Chain Endpoint (Simulation-Only)
    # ========================================================================

    if event_store is not None:
        # Cache event index to avoid O(n) rebuilds on every request
        event_index_cache: dict[str, Any] = {}
        cached_event_count = [0]  # Use list to allow modification in closure

        def _get_event_index() -> dict[str, Any]:
            """
            Get or rebuild cached event index.

            Caches the event index to avoid O(n) iteration on every causal chain request.
            The cache remains valid until new events are appended to the store or streams
            are deleted. Uses get_total_event_count() for efficient cache invalidation.

            Returns:
                Dict mapping event_id -> DomainEvent
            """
            # Use get_total_event_count() (O(1) with lock) instead of get_all_events_list()
            # to check staleness without copying the entire event list
            current_event_count = event_store.get_total_event_count()

            # Rebuild if count differs (handles both append and delete scenarios)
            if cached_event_count[0] != current_event_count:
                event_index_cache.clear()
                # Only call get_all_events_list() when cache needs rebuilding
                for event in event_store.get_all_events_list():
                    event_index_cache[str(event.event_id)] = event
                cached_event_count[0] = current_event_count

            return event_index_cache

        def _extract_payload_summary(event: Any) -> dict[str, Any]:
            """Extract a readable summary from event payload."""
            from collections.abc import Mapping

            payload = getattr(event, "payload", {})
            if not isinstance(payload, Mapping):
                return {}
            # Return only key fields for readability, limit to ~10 fields
            summary = {}
            key_fields = [
                "work_item_id",
                "workflow_id",
                "project_id",
                "from_column",
                "to_column",
                "stage",
                "status",
                "agent_id",
                "issue_id",
                "correlation_id",
            ]
            for field in key_fields:
                if field in payload:
                    summary[field] = payload[field]
            return summary

        def _get_event_timestamp(event: Any) -> datetime:
            """
            Get event timestamp using simulation clock when available.

            Uses the simulation clock for time-aware timestamps in simulation mode,
            falling back to event's occurred_at field if available, and finally to
            wall-clock time only as a last resort.

            Args:
                event: Domain event object

            Returns:
                datetime: Timestamp of event
            """
            # First try to use the event's occurred_at timestamp
            occurred_at = getattr(event, "occurred_at", None)
            if occurred_at is not None:
                return occurred_at

            # If simulation clock is available, use it for consistency
            if simulation_clock is not None:
                return simulation_clock.now()

            # Last resort: wall-clock time (only if simulation clock is unavailable)
            return datetime.now()

        async def _build_causal_chain(
            root_event_id: str, max_hops: int = 100
        ) -> tuple[list[CausalChainEvent], bool, str]:
            """
            Traverse the causal chain backward from a root event.

            Uses the cached event index for O(1) lookups. Traversal follows the causation_id
            chain from each event. Consults the CausalLinkRegistry (when provided) to annotate
            chain events with registered dependency metadata and validate structural consistency.

            Returns:
                Tuple of (chain events, truncated, root_event_id)
            """
            events_by_id = _get_event_index()

            if root_event_id not in events_by_id:
                return [], False, ""

            chain: list[CausalChainEvent] = []
            current_event_id = root_event_id
            hops = 0
            actual_root_id = root_event_id

            # Fetch registry metadata once before traversing the chain (not per-event)
            all_links = None
            if causal_link_registry is not None:
                all_links = causal_link_registry.get_all_links()

            while current_event_id and hops < max_hops:
                if current_event_id not in events_by_id:
                    break

                event = events_by_id[current_event_id]

                # Build event info for chain
                event_type = getattr(event, "event_type", None) or getattr(event, "type", None)
                causation_id = getattr(event, "causation_id", None)
                occurred_at = _get_event_timestamp(event)

                payload_summary = _extract_payload_summary(event)

                # Consult CausalLinkRegistry to enrich chain event with dependency metadata
                registry_metadata: dict[str, Any] = {}
                if causal_link_registry is not None:
                    # Get component-level links that might relate to this event
                    # by examining event type and payload fields
                    event_name = event_type or "Unknown"

                    # Check for subscriptions that publish this event type
                    subscriptions = causal_link_registry.get_subscriptions(event_type=event_name)
                    if subscriptions:
                        registry_metadata["subscriptions"] = [
                            {
                                "publisher": sub.publisher,
                                "subscriber": sub.subscriber,
                                "event_type": sub.event_type,
                            }
                            for sub in subscriptions
                        ]

                    # Check for links targeting components mentioned in the payload
                    # This enriches the chain with structural dependency info
                    # Use pre-fetched all_links instead of querying on each event
                    payload_links = []
                    if all_links:
                        for field_name, field_value in payload_summary.items():
                            # Look for links where field_value might be a component name
                            field_str = str(field_value)
                            for link in all_links:
                                if link.source == field_str or link.target == field_str:
                                    payload_links.append(
                                        {
                                            "source": link.source,
                                            "target": link.target,
                                            "link_type": (
                                                link.link_type.value
                                                if hasattr(link.link_type, "value")
                                                else str(link.link_type)
                                            ),
                                            "field": field_name,
                                        }
                                    )

                        if payload_links:
                            registry_metadata["dependency_links"] = payload_links

                chain_event = CausalChainEvent(
                    eventId=str(event.event_id),
                    eventType=event_type or "Unknown",
                    occurredAt=occurred_at,
                    causationId=str(causation_id) if causation_id else None,
                    payloadSummary=payload_summary,
                    registryMetadata=registry_metadata if registry_metadata else None,
                )
                chain.append(chain_event)

                actual_root_id = str(event.event_id)

                # Move to the causation event
                if causation_id:
                    current_event_id = str(causation_id)
                    hops += 1
                else:
                    # We've reached the root
                    break

            truncated = hops >= max_hops and current_event_id is not None

            return chain, truncated, actual_root_id

        @router.get(
            "/events/{event_id}/causal-chain",
            response_model=CausalChainResponse,
            summary="Get causal chain for an event",
            response_description="Causal chain of events",
        )
        async def get_causal_chain(
            event_id: str = Path(..., description="Event ID to trace the causal chain for (format: UUID)"),
        ) -> CausalChainResponse:
            """
            Get the causal chain for a specific event by traversing backward through causation_id.

            This endpoint traces the causation chain of domain events, showing how one event
            was caused by previous events. The chain is ordered from the queried event back
            to the root cause.

            **Path Parameters:**
            - event_id: The UUID of the event to trace

            **Returns:**
            - 200 OK: Causal chain with events in reverse chronological order (from queried to root)
            - 404 Not Found: Event with given ID does not exist
            - 500 Internal Server Error: Unexpected error during traversal

            **Examples:**
            - Get causal chain: `GET /api/v2/audit/events/abc123-def456/causal-chain`
            - Trace workflow completion: `GET /api/v2/audit/events/workflow-event-id/causal-chain`

            **Note:** This endpoint is only available in simulation mode where the event store
            is in-memory. It is not available in production deployments.
            """
            try:
                chain, truncated, root_event_id = await _build_causal_chain(event_id)

                if not chain:
                    raise HTTPException(
                        status_code=http_status.HTTP_404_NOT_FOUND,
                        detail=f"Event with ID {event_id} not found",
                    )

                return CausalChainResponse(
                    rootEventId=root_event_id,
                    chain=chain,
                    truncated=truncated,
                    hopCount=len(chain),
                )

            except HTTPException:
                raise
            except Exception as e:
                logger.error(
                    "Unexpected error building causal chain",
                    exc_info=True,
                    extra={"event_id": event_id, "error": str(e)},
                )
                raise HTTPException(
                    status_code=http_status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail="Internal server error while building causal chain",
                )

    return router
