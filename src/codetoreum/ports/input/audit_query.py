"""
Audit Query Input Port

This module defines the input port interface for querying audit events,
including filtering, pagination, and retrieval of system-wide audit logs.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from types import MappingProxyType


@dataclass(frozen=True)
class AuditEventFilters:
    """Filters for querying audit events"""

    event_type: str | None = None
    resource_type: str | None = None
    resource_id: str | None = None
    user_id: str | None = None
    action: str | None = None
    success: bool | None = None
    start_time: datetime | None = None
    end_time: datetime | None = None
    work_item_id: str | None = None


@dataclass(frozen=True)
class AuditEventPaginationParams:
    """Pagination parameters for audit event queries"""

    offset: int = 0
    limit: int = 100


@dataclass(frozen=True)
class AuditEventInfo:
    """Audit event information"""

    id: str
    timestamp: datetime
    event_type: str
    resource_type: str
    resource_id: str
    action: str
    user_id: str
    correlation_id: str | None
    metadata: MappingProxyType[str, object]
    success: bool
    error_message: str | None


@dataclass(frozen=True)
class AuditEventQueryResult:
    """Result of audit event query"""

    events: tuple[AuditEventInfo, ...]
    total_count: int
    offset: int
    limit: int

    @property
    def has_next(self) -> bool:
        """Check if there are more results"""
        return (self.offset + self.limit) < self.total_count


class IAuditQueryPort(ABC):
    """
    Input port for querying audit events.

    This port provides access to system-wide audit logs with filtering,
    pagination, and search capabilities.
    """

    @abstractmethod
    async def query_audit_events(
        self,
        filters: AuditEventFilters | None = None,
        pagination: AuditEventPaginationParams | None = None,
    ) -> AuditEventQueryResult:
        """
        Query audit events with optional filtering and pagination.

        Args: filters: Optional filters to apply to the query
            pagination: Optional pagination parameters

        Returns: AuditEventQueryResult with matching events and pagination info
        """
