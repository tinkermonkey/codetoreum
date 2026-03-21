"""
Audit Store Interfaces

Defines the abstract interface for audit log storage backends.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from typing import Any


@dataclass
class AuditQueryFilters:
    """Filters for querying audit logs."""

    event_type: str | None = None
    resource_type: str | None = None
    resource_id: str | None = None
    user_id: str | None = None
    action: str | None = None
    success: bool | None = None
    start_time: datetime | None = None
    end_time: datetime | None = None
    work_item_id: str | None = None
    limit: int = 100
    offset: int = 0


class IAuditStore(ABC):
    """
    Abstract interface for audit log storage.

    Implementations can store audit events in various backends:
    - PostgreSQL (production - separate audit database)
    - SQLite (development/testing)
    - In-memory (simulation/testing)
    - Elasticsearch (for advanced search/analytics)
    """

    @abstractmethod
    async def store_event(
        self,
        timestamp: datetime,
        event_type: str,
        resource_type: str,
        resource_id: str,
        action: str,
        user_id: str,
        correlation_id: str | None,
        metadata: dict[str, Any],
        success: bool,
        error_message: str | None = None,
    ) -> str:
        """
        Store an audit event.

        Args:
            timestamp: When the event occurred
            event_type: Type of event (e.g., "agent_deleted")
            resource_type: Type of resource (e.g., "agent")
            resource_id: ID of the resource
            action: Action performed (e.g., "delete")
            user_id: ID of user who performed the action
            correlation_id: Optional correlation ID for request tracing
            metadata: Additional event metadata
            success: Whether the action succeeded
            error_message: Optional error message if action failed

        Returns:
            ID of the stored audit event
        """

    @abstractmethod
    async def query_events(self, filters: AuditQueryFilters) -> list[dict[str, Any]]:
        """
        Query audit events with filters.

        Args:
            filters: Query filters

        Returns:
            List of matching audit events
        """

    @abstractmethod
    async def count_events(self, filters: AuditQueryFilters) -> int:
        """
        Count audit events matching filters.

        Args:
            filters: Query filters

        Returns:
            Number of matching events
        """

    @abstractmethod
    async def cleanup_old_events(self, retention_days: int) -> int:
        """
        Delete audit events older than retention period.

        Args:
            retention_days: Number of days to retain events

        Returns:
            Number of events deleted
        """

    @abstractmethod
    async def get_event_by_id(self, event_id: str) -> dict[str, Any] | None:
        """
        Retrieve a specific audit event by ID.

        Args:
            event_id: ID of the event

        Returns:
            Event data or None if not found
        """
