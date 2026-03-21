"""
Audit Store Implementations

Provides concrete implementations of the IAuditStore interface for different
storage backends.
"""

import json
import logging
from collections import OrderedDict, defaultdict
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import uuid4

import aiofiles

from codetoreum.infrastructure.audit.interfaces import AuditQueryFilters, IAuditStore

logger = logging.getLogger(__name__)


class InMemoryAuditStore(IAuditStore):
    """
    In-memory audit store for development and testing.

    This store keeps all events in memory and provides fast querying with LRU eviction.
    It's suitable for:
    - Unit tests
    - Integration tests
    - Simulation tests
    - Local development

    NOT suitable for production (events lost on restart, no persistence).

    Features size limits with LRU eviction to prevent unbounded memory growth.
    """

    def __init__(self, max_events: int = 10000):
        """
        Initialize in-memory storage.

        Args:
            max_events: Maximum number of events to keep in memory.
                       Oldest events are evicted when limit is reached.
                       Default: 10000 events
        """
        self.max_events = max_events
        self._events: OrderedDict[str, dict[str, Any]] = OrderedDict()
        self._index_by_type: dict[str, list[str]] = defaultdict(list)
        self._index_by_resource: dict[str, list[str]] = defaultdict(list)
        self._index_by_user: dict[str, list[str]] = defaultdict(list)

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
        """Store an audit event in memory with LRU eviction."""
        event_id = str(uuid4())

        event = {
            "id": event_id,
            "timestamp": timestamp,
            "event_type": event_type,
            "resource_type": resource_type,
            "resource_id": resource_id,
            "action": action,
            "user_id": user_id,
            "correlation_id": correlation_id,
            "metadata": metadata,
            "success": success,
            "error_message": error_message,
        }

        # LRU eviction: Remove oldest event if at max capacity
        if len(self._events) >= self.max_events:
            oldest_event_id, oldest_event = self._events.popitem(last=False)
            self._remove_from_indexes(oldest_event_id, oldest_event)
            logger.debug(f"Evicted oldest audit event {oldest_event_id} to maintain max_events={self.max_events}")

        # Store event
        self._events[event_id] = event

        # Update indexes for fast querying
        self._index_by_type[event_type].append(event_id)
        resource_key = f"{resource_type}:{resource_id}"
        self._index_by_resource[resource_key].append(event_id)
        self._index_by_user[user_id].append(event_id)

        return event_id

    def _remove_from_indexes(self, event_id: str, event: dict[str, Any]) -> None:
        """Remove event from all indexes."""
        event_type = event["event_type"]
        if event_id in self._index_by_type[event_type]:
            self._index_by_type[event_type].remove(event_id)

        resource_key = f"{event['resource_type']}:{event['resource_id']}"
        if event_id in self._index_by_resource[resource_key]:
            self._index_by_resource[resource_key].remove(event_id)

        user_id = event["user_id"]
        if event_id in self._index_by_user[user_id]:
            self._index_by_user[user_id].remove(event_id)

    async def query_events(self, filters: AuditQueryFilters) -> list[dict[str, Any]]:
        """Query audit events with filters."""
        # Start with all events
        matching_events = list(self._events.values())

        # Apply filters
        if filters.event_type:
            matching_events = [e for e in matching_events if e["event_type"] == filters.event_type]

        if filters.resource_type:
            matching_events = [e for e in matching_events if e["resource_type"] == filters.resource_type]

        if filters.resource_id:
            matching_events = [e for e in matching_events if e["resource_id"] == filters.resource_id]

        if filters.user_id:
            matching_events = [e for e in matching_events if e["user_id"] == filters.user_id]

        if filters.action:
            matching_events = [e for e in matching_events if e["action"] == filters.action]

        if filters.success is not None:
            matching_events = [e for e in matching_events if e["success"] == filters.success]

        if filters.start_time:
            matching_events = [e for e in matching_events if e["timestamp"] >= filters.start_time]

        if filters.end_time:
            matching_events = [e for e in matching_events if e["timestamp"] <= filters.end_time]

        if filters.work_item_id:
            matching_events = [
                e
                for e in matching_events
                if (
                    e.get("resource_id") == filters.work_item_id
                    or filters.work_item_id in str(e.get("metadata", {}))
                    or filters.work_item_id in str(e.get("correlation_id", ""))
                )
            ]

        # Sort by timestamp (newest first)
        matching_events.sort(key=lambda e: e["timestamp"], reverse=True)

        # Apply pagination
        start = filters.offset
        end = start + filters.limit
        return matching_events[start:end]

    async def count_events(self, filters: AuditQueryFilters) -> int:
        """Count audit events matching filters."""
        events = await self.query_events(
            AuditQueryFilters(
                event_type=filters.event_type,
                resource_type=filters.resource_type,
                resource_id=filters.resource_id,
                user_id=filters.user_id,
                action=filters.action,
                success=filters.success,
                start_time=filters.start_time,
                end_time=filters.end_time,
                work_item_id=filters.work_item_id,
                limit=1000000,  # Get all for counting
                offset=0,
            )
        )
        return len(events)

    async def cleanup_old_events(self, retention_days: int) -> int:
        """Delete audit events older than retention period."""
        cutoff_date = datetime.now(UTC) - timedelta(days=retention_days)

        # Find old events
        old_event_ids = [event_id for event_id, event in self._events.items() if event["timestamp"] < cutoff_date]
        deleted_count = len(old_event_ids)

        # Remove from main storage and indexes
        for event_id in old_event_ids:
            event = self._events[event_id]
            del self._events[event_id]
            self._remove_from_indexes(event_id, event)

        logger.info(f"Cleaned up {deleted_count} old audit events")
        return deleted_count

    async def get_event_by_id(self, event_id: str) -> dict[str, Any] | None:
        """Retrieve a specific audit event by ID."""
        return self._events.get(event_id)

    def clear(self) -> None:
        """Clear all events (for testing)."""
        self._events.clear()
        self._index_by_type.clear()
        self._index_by_resource.clear()
        self._index_by_user.clear()

    def get_stats(self) -> dict[str, Any]:
        """Get statistics about stored events."""
        return {
            "total_events": len(self._events),
            "max_events": self.max_events,
            "events_by_type": {event_type: len(event_ids) for event_type, event_ids in self._index_by_type.items()},
            "users": len(self._index_by_user),
        }


class FileAuditStore(IAuditStore):
    """
    File-based audit store for simple persistent storage.

    Stores audit events as newline-delimited JSON (NDJSON) in a file.
    Suitable for:
    - Small-scale deployments
    - Development environments
    - Proof-of-concept implementations

    For production at scale, use PostgreSQLAuditStore or ElasticsearchAuditStore.
    """

    def __init__(self, file_path: str):
        """
        Initialize file-based audit store.

        Args:
            file_path: Path to audit log file
        """
        self.file_path = file_path

    async def _ensure_file_exists(self) -> None:
        """Ensure the audit log file exists."""
        try:
            async with aiofiles.open(self.file_path, "a"):
                pass
        except Exception as e:
            logger.error(
                f"Failed to create audit log file: {e}",
                exc_info=True,
                extra={"error_id": "ERR_AUDIT_STORE_DIRECTORY_FAILED"},
            )

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
        """Store an audit event to file using async I/O."""
        await self._ensure_file_exists()

        event_id = str(uuid4())

        event = {
            "id": event_id,
            "timestamp": timestamp.isoformat(),
            "event_type": event_type,
            "resource_type": resource_type,
            "resource_id": resource_id,
            "action": action,
            "user_id": user_id,
            "correlation_id": correlation_id,
            "metadata": metadata,
            "success": success,
            "error_message": error_message,
        }

        try:
            async with aiofiles.open(self.file_path, "a") as f:
                await f.write(json.dumps(event) + "\n")
        except Exception as e:
            logger.error(
                f"Failed to write audit event to file: {e}",
                exc_info=True,
                extra={"error_id": "ERR_AUDIT_STORE_WRITE_EVENT_FAILED"},
            )
            # Don't raise - audit failures shouldn't break the application

        return event_id

    async def query_events(self, filters: AuditQueryFilters) -> list[dict[str, Any]]:
        """
        Query audit events from file using async I/O.

        Note: This reads the entire file and filters in memory.
        For large audit logs, use a database backend.
        """
        matching_events = []

        try:
            async with aiofiles.open(self.file_path) as f:
                async for line in f:
                    if not line.strip():
                        continue

                    event = json.loads(line)

                    # Parse timestamp
                    event["timestamp"] = datetime.fromisoformat(event["timestamp"])

                    # Apply filters
                    if filters.event_type and event["event_type"] != filters.event_type:
                        continue
                    if filters.resource_type and event["resource_type"] != filters.resource_type:
                        continue
                    if filters.resource_id and event["resource_id"] != filters.resource_id:
                        continue
                    if filters.user_id and event["user_id"] != filters.user_id:
                        continue
                    if filters.action and event["action"] != filters.action:
                        continue
                    if filters.success is not None and event["success"] != filters.success:
                        continue
                    if filters.start_time and event["timestamp"] < filters.start_time:
                        continue
                    if filters.end_time and event["timestamp"] > filters.end_time:
                        continue
                    if filters.work_item_id and not (
                        event.get("resource_id") == filters.work_item_id
                        or filters.work_item_id in str(event.get("metadata", {}))
                        or filters.work_item_id in str(event.get("correlation_id", ""))
                    ):
                        continue

                    matching_events.append(event)

        except FileNotFoundError:
            logger.warning(f"Audit log file not found: {self.file_path}")
            return []
        except Exception as e:
            logger.error(
                f"Failed to read audit log file: {e}",
                exc_info=True,
                extra={"error_id": "ERR_AUDIT_STORE_READ_EVENTS_FAILED"},
            )
            return []

        # Sort by timestamp (newest first)
        matching_events.sort(key=lambda e: e["timestamp"], reverse=True)

        # Apply pagination
        start = filters.offset
        end = start + filters.limit
        return matching_events[start:end]

    async def count_events(self, filters: AuditQueryFilters) -> int:
        """Count audit events matching filters."""
        events = await self.query_events(
            AuditQueryFilters(
                event_type=filters.event_type,
                resource_type=filters.resource_type,
                resource_id=filters.resource_id,
                user_id=filters.user_id,
                action=filters.action,
                success=filters.success,
                start_time=filters.start_time,
                end_time=filters.end_time,
                work_item_id=filters.work_item_id,
                limit=1000000,  # Get all for counting
                offset=0,
            )
        )
        return len(events)

    async def cleanup_old_events(self, retention_days: int) -> int:
        """
        Delete audit events older than retention period using async I/O.

        Note: This rewrites the entire file. For production,
        use a database backend with efficient deletion.
        """
        cutoff_date = datetime.now(UTC) - timedelta(days=retention_days)
        kept_events = []
        deleted_count = 0

        try:
            # Read all events
            async with aiofiles.open(self.file_path) as f:
                async for line in f:
                    if not line.strip():
                        continue

                    event = json.loads(line)
                    event_time = datetime.fromisoformat(event["timestamp"])

                    if event_time >= cutoff_date:
                        kept_events.append(line)
                    else:
                        deleted_count += 1

            # Rewrite file with kept events
            async with aiofiles.open(self.file_path, "w") as f:
                for line in kept_events:
                    await f.write(line)

            logger.info(f"Cleaned up {deleted_count} old audit events")

        except Exception as e:
            logger.error(
                f"Failed to cleanup old audit events: {e}",
                exc_info=True,
                extra={"error_id": "ERR_AUDIT_STORE_CLEANUP_FAILED"},
            )

        return deleted_count

    async def get_event_by_id(self, event_id: str) -> dict[str, Any] | None:
        """Retrieve a specific audit event by ID using async I/O."""
        try:
            async with aiofiles.open(self.file_path) as f:
                async for line in f:
                    if not line.strip():
                        continue

                    event = json.loads(line)
                    if event["id"] == event_id:
                        event["timestamp"] = datetime.fromisoformat(event["timestamp"])
                        return event

        except Exception as e:
            logger.error(
                f"Failed to retrieve audit event: {e}",
                exc_info=True,
                extra={"error_id": "ERR_AUDIT_STORE_RETRIEVE_FAILED"},
            )

        return None


class PostgreSQLAuditStore(IAuditStore):
    """
    PostgreSQL-backed audit store for production use.

    Provides:
    - Durable persistent storage
    - Indexed queries for fast lookups
    - Efficient pagination
    - Transaction support
    - Suitable for high-volume production environments

    Requires:
    - asyncpg driver
    - PostgreSQL 12+ database

    Table schema:
        CREATE TABLE audit_events (
            id UUID PRIMARY KEY,
            timestamp TIMESTAMP WITH TIME ZONE NOT NULL,
            event_type VARCHAR(100) NOT NULL,
            resource_type VARCHAR(100) NOT NULL,
            resource_id VARCHAR(255) NOT NULL,
            action VARCHAR(50) NOT NULL,
            user_id VARCHAR(255) NOT NULL,
            correlation_id UUID,
            metadata JSONB,
            success BOOLEAN NOT NULL,
            error_message TEXT,
            created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
        );

        -- Indexes for common query patterns
        CREATE INDEX idx_audit_timestamp ON audit_events(timestamp DESC);
        CREATE INDEX idx_audit_event_type ON audit_events(event_type);
        CREATE INDEX idx_audit_resource ON audit_events(resource_type, resource_id);
        CREATE INDEX idx_audit_user ON audit_events(user_id);
        CREATE INDEX idx_audit_correlation ON audit_events(correlation_id);
    """

    def __init__(self, connection_string: str):
        """
        Initialize PostgreSQL audit store.

        Args:
            connection_string: PostgreSQL connection string
                              (e.g., "postgresql+asyncpg://user:pass@host/db")
        """
        from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
        from sqlalchemy.orm import sessionmaker

        self.engine = create_async_engine(connection_string, echo=False)
        self.async_session = sessionmaker(self.engine, class_=AsyncSession, expire_on_commit=False)

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
        """Store an audit event in PostgreSQL."""
        from sqlalchemy import text

        event_id = str(uuid4())

        async with self.async_session() as session:
            try:
                await session.execute(
                    text("""
                        INSERT INTO audit_events (
                            id, timestamp, event_type, resource_type, resource_id,
                            action, user_id, correlation_id, metadata, success, error_message
                        ) VALUES (
                            :id, :timestamp, :event_type, :resource_type, :resource_id,
                            :action, :user_id, :correlation_id, :metadata::jsonb, :success, :error_message
                        )
                        """),
                    {
                        "id": event_id,
                        "timestamp": timestamp,
                        "event_type": event_type,
                        "resource_type": resource_type,
                        "resource_id": resource_id,
                        "action": action,
                        "user_id": user_id,
                        "correlation_id": correlation_id,
                        "metadata": json.dumps(metadata),
                        "success": success,
                        "error_message": error_message,
                    },
                )
                await session.commit()
            except Exception as e:
                logger.error(
                    f"Failed to store audit event in PostgreSQL: {e}",
                    exc_info=True,
                    extra={"error_id": "ERR_AUDIT_POSTGRES_STORE_FAILED"},
                )
                await session.rollback()
                # Don't raise - audit failures shouldn't break the application

        return event_id

    async def query_events(self, filters: AuditQueryFilters) -> list[dict[str, Any]]:
        """Query audit events from PostgreSQL with efficient indexed lookups."""
        from sqlalchemy import text

        # Build WHERE clause dynamically based on filters
        where_clauses = []
        params = {}

        if filters.event_type:
            where_clauses.append("event_type = :event_type")
            params["event_type"] = filters.event_type

        if filters.resource_type:
            where_clauses.append("resource_type = :resource_type")
            params["resource_type"] = filters.resource_type

        if filters.resource_id:
            where_clauses.append("resource_id = :resource_id")
            params["resource_id"] = filters.resource_id

        if filters.user_id:
            where_clauses.append("user_id = :user_id")
            params["user_id"] = filters.user_id

        if filters.action:
            where_clauses.append("action = :action")
            params["action"] = filters.action

        if filters.success is not None:
            where_clauses.append("success = :success")
            params["success"] = filters.success

        if filters.start_time:
            where_clauses.append("timestamp >= :start_time")
            params["start_time"] = filters.start_time

        if filters.end_time:
            where_clauses.append("timestamp <= :end_time")
            params["end_time"] = filters.end_time

        if filters.work_item_id:
            where_clauses.append(
                "(resource_id = :work_item_id OR "
                "metadata::text LIKE :work_item_id_metadata OR "
                "correlation_id::text LIKE :work_item_id_correlation)"
            )
            params["work_item_id"] = filters.work_item_id
            params["work_item_id_metadata"] = f"%{filters.work_item_id}%"
            params["work_item_id_correlation"] = f"%{filters.work_item_id}%"

        where_sql = "WHERE " + " AND ".join(where_clauses) if where_clauses else ""

        params["limit"] = filters.limit
        params["offset"] = filters.offset

        query = f"""
            SELECT
                id, timestamp, event_type, resource_type, resource_id,
                action, user_id, correlation_id, metadata, success, error_message
            FROM audit_events
            {where_sql}
            ORDER BY timestamp DESC
            LIMIT :limit OFFSET :offset
        """

        async with self.async_session() as session:
            try:
                result = await session.execute(text(query), params)
                rows = result.fetchall()

                events = []
                for row in rows:
                    events.append(
                        {
                            "id": str(row[0]),
                            "timestamp": row[1],
                            "event_type": row[2],
                            "resource_type": row[3],
                            "resource_id": row[4],
                            "action": row[5],
                            "user_id": row[6],
                            "correlation_id": str(row[7]) if row[7] else None,
                            "metadata": row[8],
                            "success": row[9],
                            "error_message": row[10],
                        }
                    )

                return events

            except Exception as e:
                logger.error(
                    f"Failed to query audit events from PostgreSQL: {e}",
                    exc_info=True,
                    extra={"error_id": "ERR_AUDIT_POSTGRES_READ_EVENTS_FAILED"},
                )
                return []

    async def count_events(self, filters: AuditQueryFilters) -> int:
        """Count audit events matching filters."""
        from sqlalchemy import text

        # Build WHERE clause (same as query_events)
        where_clauses = []
        params = {}

        if filters.event_type:
            where_clauses.append("event_type = :event_type")
            params["event_type"] = filters.event_type

        if filters.resource_type:
            where_clauses.append("resource_type = :resource_type")
            params["resource_type"] = filters.resource_type

        if filters.resource_id:
            where_clauses.append("resource_id = :resource_id")
            params["resource_id"] = filters.resource_id

        if filters.user_id:
            where_clauses.append("user_id = :user_id")
            params["user_id"] = filters.user_id

        if filters.action:
            where_clauses.append("action = :action")
            params["action"] = filters.action

        if filters.success is not None:
            where_clauses.append("success = :success")
            params["success"] = filters.success

        if filters.start_time:
            where_clauses.append("timestamp >= :start_time")
            params["start_time"] = filters.start_time

        if filters.end_time:
            where_clauses.append("timestamp <= :end_time")
            params["end_time"] = filters.end_time

        if filters.work_item_id:
            where_clauses.append(
                "(resource_id = :work_item_id OR "
                "metadata::text LIKE :work_item_id_metadata OR "
                "correlation_id::text LIKE :work_item_id_correlation)"
            )
            params["work_item_id"] = filters.work_item_id
            params["work_item_id_metadata"] = f"%{filters.work_item_id}%"
            params["work_item_id_correlation"] = f"%{filters.work_item_id}%"

        where_sql = "WHERE " + " AND ".join(where_clauses) if where_clauses else ""

        query = f"""
            SELECT COUNT(*) FROM audit_events {where_sql}
        """

        async with self.async_session() as session:
            try:
                result = await session.execute(text(query), params)
                count = result.scalar()
                return count or 0
            except Exception as e:
                logger.error(
                    f"Failed to count audit events in PostgreSQL: {e}",
                    exc_info=True,
                    extra={"error_id": "ERR_AUDIT_POSTGRES_COUNT_FAILED"},
                )
                return 0

    async def cleanup_old_events(self, retention_days: int) -> int:
        """Delete audit events older than retention period efficiently."""
        from sqlalchemy import text

        cutoff_date = datetime.now(UTC) - timedelta(days=retention_days)

        async with self.async_session() as session:
            try:
                result = await session.execute(
                    text("DELETE FROM audit_events WHERE timestamp < :cutoff"),
                    {"cutoff": cutoff_date},
                )
                deleted_count = result.rowcount
                await session.commit()

                logger.info(f"Cleaned up {deleted_count} old audit events from PostgreSQL")
                return deleted_count

            except Exception as e:
                logger.error(
                    f"Failed to cleanup old audit events in PostgreSQL: {e}",
                    exc_info=True,
                    extra={"error_id": "ERR_AUDIT_POSTGRES_CLEANUP_FAILED"},
                )
                await session.rollback()
                return 0

    async def get_event_by_id(self, event_id: str) -> dict[str, Any] | None:
        """Retrieve a specific audit event by ID."""
        from sqlalchemy import text

        async with self.async_session() as session:
            try:
                result = await session.execute(
                    text("""
                        SELECT
                            id, timestamp, event_type, resource_type, resource_id,
                            action, user_id, correlation_id, metadata, success, error_message
                        FROM audit_events
                        WHERE id = :id
                        """),
                    {"id": event_id},
                )
                row = result.fetchone()

                if not row:
                    return None

                return {
                    "id": str(row[0]),
                    "timestamp": row[1],
                    "event_type": row[2],
                    "resource_type": row[3],
                    "resource_id": row[4],
                    "action": row[5],
                    "user_id": row[6],
                    "correlation_id": str(row[7]) if row[7] else None,
                    "metadata": row[8],
                    "success": row[9],
                    "error_message": row[10],
                }

            except Exception as e:
                logger.error(
                    f"Failed to retrieve audit event from PostgreSQL: {e}",
                    exc_info=True,
                    extra={"error_id": "ERR_AUDIT_POSTGRES_RETRIEVE_FAILED"},
                )
                return None

    async def close(self) -> None:
        """Close database connection."""
        await self.engine.dispose()


# TODO: Add ElasticsearchAuditStore for advanced search/analytics
