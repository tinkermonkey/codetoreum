"""
Mock Audit Query Adapter

In-memory implementation of IAuditQueryPort for development and testing.
Integrates with InMemoryAuditStore for audit event storage and retrieval.
"""

import logging
from types import MappingProxyType

from codetoreum.infrastructure.audit.interfaces import (
    AuditQueryFilters,
    IAuditStore,
)
from codetoreum.ports.input.audit_query import (
    AuditEventFilters,
    AuditEventInfo,
    AuditEventPaginationParams,
    AuditEventQueryResult,
    IAuditQueryPort,
)

logger = logging.getLogger(__name__)


class MockAuditQueryAdapter(IAuditQueryPort):
    """
    Mock implementation of IAuditQueryPort using in-memory storage.

    Integrates with InMemoryAuditStore for audit event storage and query operations.
    """

    def __init__(self, audit_store: IAuditStore):
        """
        Initialize the mock audit query adapter.

        Args:
            audit_store: The audit store backend to query
        """
        self.audit_store = audit_store

    async def query_audit_events(
        self,
        filters: AuditEventFilters | None = None,
        pagination: AuditEventPaginationParams | None = None,
    ) -> AuditEventQueryResult:
        """
        Query audit events with optional filtering and pagination.

        Args:
            filters: Optional filters to apply to the query
            pagination: Optional pagination parameters

        Returns:
            AuditEventQueryResult with matching events and pagination info
        """
        # Set defaults
        if pagination is None:
            pagination = AuditEventPaginationParams()

        # Convert filters to audit store format
        store_filters = AuditQueryFilters(
            event_type=filters.event_type if filters else None,
            resource_type=filters.resource_type if filters else None,
            resource_id=filters.resource_id if filters else None,
            user_id=filters.user_id if filters else None,
            action=filters.action if filters else None,
            success=filters.success if filters else None,
            start_time=filters.start_time if filters else None,
            end_time=filters.end_time if filters else None,
            work_item_id=filters.work_item_id if filters else None,
            limit=pagination.limit,
            offset=pagination.offset,
        )

        # Query events from store
        event_dicts = await self.audit_store.query_events(store_filters)

        # Get total count
        count_filters = AuditQueryFilters(
            event_type=store_filters.event_type,
            resource_type=store_filters.resource_type,
            resource_id=store_filters.resource_id,
            user_id=store_filters.user_id,
            action=store_filters.action,
            success=store_filters.success,
            start_time=store_filters.start_time,
            end_time=store_filters.end_time,
            work_item_id=store_filters.work_item_id,
        )
        total_count = await self.audit_store.count_events(count_filters)

        # Convert to result format
        events = []
        for event_dict in event_dicts:
            # Validate required fields for audit integrity
            required_fields = {
                "id": event_dict.get("id"),
                "timestamp": event_dict.get("timestamp"),
                "event_type": event_dict.get("event_type"),
                "resource_type": event_dict.get("resource_type"),
                "resource_id": event_dict.get("resource_id"),
                "action": event_dict.get("action"),
                "user_id": event_dict.get("user_id"),
            }

            # Check for missing or empty required fields
            missing_fields = [name for name, value in required_fields.items() if not value]
            if missing_fields:
                logger.error(
                    "Audit event missing required fields",
                    extra={
                        "event_id": event_dict.get("id"),
                        "missing_fields": missing_fields,
                    },
                )
                raise RuntimeError(
                    f"Audit data integrity error: event {event_dict.get('id')} missing required fields: {missing_fields}"
                )

            event_info = AuditEventInfo(
                id=required_fields["id"],
                timestamp=required_fields["timestamp"],
                event_type=required_fields["event_type"],
                resource_type=required_fields["resource_type"],
                resource_id=required_fields["resource_id"],
                action=required_fields["action"],
                user_id=required_fields["user_id"],
                correlation_id=event_dict.get("correlation_id"),
                metadata=MappingProxyType(event_dict.get("metadata", {})),
                success=event_dict.get("success", False),
                error_message=event_dict.get("error_message"),
            )
            events.append(event_info)

        return AuditEventQueryResult(
            events=tuple(events),
            total_count=total_count,
            offset=pagination.offset,
            limit=pagination.limit,
        )
