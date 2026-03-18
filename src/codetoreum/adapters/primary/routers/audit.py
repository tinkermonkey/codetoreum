"""
Audit Events REST API Router

Provides RESTful endpoints for querying system-wide audit events.
"""

import logging
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi import status as http_status

from codetoreum.adapters.primary.audit_dtos import AuditEventsListResponse
from codetoreum.adapters.primary.simple_auth_dependencies import SimpleAuthDependencies
from codetoreum.config import DEFAULT_OFFSET
from codetoreum.config.defaults import AUDIT_EVENTS_MAX_PAGE_SIZE
from codetoreum.ports.input.audit_query import (
    AuditEventFilters,
    AuditEventPaginationParams,
    IAuditQueryPort,
)

logger = logging.getLogger(__name__)


def create_audit_router(
    query_port: IAuditQueryPort,
    auth_deps: SimpleAuthDependencies | None = None,
) -> APIRouter:
    """
    Create the audit events REST API router.

    Args:
        query_port: Audit query input port
        auth_deps: Optional authentication dependencies

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
        - Paginate: `GET /api/v2/audit/events?offset=20&limit=20`
        """
        try:
            # Build filters
            filters = None
            if any([eventType, resourceType, resourceId, userId, action, success is not None, startTime, endTime]):
                filters = AuditEventFilters(
                    event_type=eventType,
                    resource_type=resourceType,
                    resource_id=resourceId,
                    user_id=userId,
                    action=action,
                    success=success,
                    start_time=startTime,
                    end_time=endTime,
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

    return router
