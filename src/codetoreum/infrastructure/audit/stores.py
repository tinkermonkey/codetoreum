"""
Audit Store Implementations

Provides concrete implementations of the IAuditStore interface for different
storage backends.
"""

import json
import logging
from collections import defaultdict
from datetime import datetime, timedelta
from typing import List, Optional, Dict, Any
from uuid import uuid4

from codetoreum.infrastructure.audit.interfaces import IAuditStore, AuditQueryFilters

logger = logging.getLogger(__name__)


class InMemoryAuditStore(IAuditStore):
    """
    In-memory audit store for development and testing.

    This store keeps all events in memory and provides fast querying.
    It's suitable for:
    - Unit tests
    - Integration tests
    - Simulation tests
    - Local development

    NOT suitable for production (events lost on restart, no persistence).
    """

    def __init__(self):
        """Initialize in-memory storage."""
        self._events: List[Dict[str, Any]] = []
        self._events_by_id: Dict[str, Dict[str, Any]] = {}
        self._index_by_type: Dict[str, List[str]] = defaultdict(list)
        self._index_by_resource: Dict[str, List[str]] = defaultdict(list)
        self._index_by_user: Dict[str, List[str]] = defaultdict(list)

    async def store_event(
        self,
        timestamp: datetime,
        event_type: str,
        resource_type: str,
        resource_id: str,
        action: str,
        user_id: str,
        correlation_id: Optional[str],
        metadata: Dict[str, Any],
        success: bool,
        error_message: Optional[str] = None,
    ) -> str:
        """Store an audit event in memory."""
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

        # Store event
        self._events.append(event)
        self._events_by_id[event_id] = event

        # Update indexes for fast querying
        self._index_by_type[event_type].append(event_id)
        resource_key = f"{resource_type}:{resource_id}"
        self._index_by_resource[resource_key].append(event_id)
        self._index_by_user[user_id].append(event_id)

        return event_id

    async def query_events(
        self, filters: AuditQueryFilters
    ) -> List[Dict[str, Any]]:
        """Query audit events with filters."""
        # Start with all events
        matching_events = list(self._events)

        # Apply filters
        if filters.event_type:
            matching_events = [
                e for e in matching_events if e["event_type"] == filters.event_type
            ]

        if filters.resource_type:
            matching_events = [
                e
                for e in matching_events
                if e["resource_type"] == filters.resource_type
            ]

        if filters.resource_id:
            matching_events = [
                e for e in matching_events if e["resource_id"] == filters.resource_id
            ]

        if filters.user_id:
            matching_events = [
                e for e in matching_events if e["user_id"] == filters.user_id
            ]

        if filters.action:
            matching_events = [
                e for e in matching_events if e["action"] == filters.action
            ]

        if filters.success is not None:
            matching_events = [
                e for e in matching_events if e["success"] == filters.success
            ]

        if filters.start_time:
            matching_events = [
                e for e in matching_events if e["timestamp"] >= filters.start_time
            ]

        if filters.end_time:
            matching_events = [
                e for e in matching_events if e["timestamp"] <= filters.end_time
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
                limit=1000000,  # Get all for counting
                offset=0,
            )
        )
        return len(events)

    async def cleanup_old_events(self, retention_days: int) -> int:
        """Delete audit events older than retention period."""
        cutoff_date = datetime.utcnow() - timedelta(days=retention_days)

        # Find old events
        old_events = [e for e in self._events if e["timestamp"] < cutoff_date]
        deleted_count = len(old_events)

        # Remove from main list
        self._events = [e for e in self._events if e["timestamp"] >= cutoff_date]

        # Remove from indexes
        for event in old_events:
            event_id = event["id"]
            del self._events_by_id[event_id]

            # Clean up indexes
            event_type = event["event_type"]
            if event_id in self._index_by_type[event_type]:
                self._index_by_type[event_type].remove(event_id)

            resource_key = f"{event['resource_type']}:{event['resource_id']}"
            if event_id in self._index_by_resource[resource_key]:
                self._index_by_resource[resource_key].remove(event_id)

            user_id = event["user_id"]
            if event_id in self._index_by_user[user_id]:
                self._index_by_user[user_id].remove(event_id)

        logger.info(f"Cleaned up {deleted_count} old audit events")
        return deleted_count

    async def get_event_by_id(self, event_id: str) -> Optional[Dict[str, Any]]:
        """Retrieve a specific audit event by ID."""
        return self._events_by_id.get(event_id)

    def clear(self) -> None:
        """Clear all events (for testing)."""
        self._events.clear()
        self._events_by_id.clear()
        self._index_by_type.clear()
        self._index_by_resource.clear()
        self._index_by_user.clear()

    def get_stats(self) -> Dict[str, Any]:
        """Get statistics about stored events."""
        return {
            "total_events": len(self._events),
            "events_by_type": {
                event_type: len(event_ids)
                for event_type, event_ids in self._index_by_type.items()
            },
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
        self._ensure_file_exists()

    def _ensure_file_exists(self) -> None:
        """Ensure the audit log file exists."""
        try:
            with open(self.file_path, "a"):
                pass
        except Exception as e:
            logger.error(f"Failed to create audit log file: {e}")

    async def store_event(
        self,
        timestamp: datetime,
        event_type: str,
        resource_type: str,
        resource_id: str,
        action: str,
        user_id: str,
        correlation_id: Optional[str],
        metadata: Dict[str, Any],
        success: bool,
        error_message: Optional[str] = None,
    ) -> str:
        """Store an audit event to file."""
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
            with open(self.file_path, "a") as f:
                f.write(json.dumps(event) + "\n")
        except Exception as e:
            logger.error(f"Failed to write audit event to file: {e}")
            # Don't raise - audit failures shouldn't break the application

        return event_id

    async def query_events(
        self, filters: AuditQueryFilters
    ) -> List[Dict[str, Any]]:
        """
        Query audit events from file.

        Note: This reads the entire file and filters in memory.
        For large audit logs, use a database backend.
        """
        matching_events = []

        try:
            with open(self.file_path, "r") as f:
                for line in f:
                    if not line.strip():
                        continue

                    event = json.loads(line)

                    # Parse timestamp
                    event["timestamp"] = datetime.fromisoformat(event["timestamp"])

                    # Apply filters
                    if filters.event_type and event["event_type"] != filters.event_type:
                        continue
                    if (
                        filters.resource_type
                        and event["resource_type"] != filters.resource_type
                    ):
                        continue
                    if (
                        filters.resource_id
                        and event["resource_id"] != filters.resource_id
                    ):
                        continue
                    if filters.user_id and event["user_id"] != filters.user_id:
                        continue
                    if filters.action and event["action"] != filters.action:
                        continue
                    if filters.success is not None and event["success"] != filters.success:
                        continue
                    if (
                        filters.start_time
                        and event["timestamp"] < filters.start_time
                    ):
                        continue
                    if filters.end_time and event["timestamp"] > filters.end_time:
                        continue

                    matching_events.append(event)

        except FileNotFoundError:
            logger.warning(f"Audit log file not found: {self.file_path}")
            return []
        except Exception as e:
            logger.error(f"Failed to read audit log file: {e}")
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
                limit=1000000,  # Get all for counting
                offset=0,
            )
        )
        return len(events)

    async def cleanup_old_events(self, retention_days: int) -> int:
        """
        Delete audit events older than retention period.

        Note: This rewrites the entire file. For production,
        use a database backend with efficient deletion.
        """
        cutoff_date = datetime.utcnow() - timedelta(days=retention_days)
        kept_events = []
        deleted_count = 0

        try:
            # Read all events
            with open(self.file_path, "r") as f:
                for line in f:
                    if not line.strip():
                        continue

                    event = json.loads(line)
                    event_time = datetime.fromisoformat(event["timestamp"])

                    if event_time >= cutoff_date:
                        kept_events.append(line)
                    else:
                        deleted_count += 1

            # Rewrite file with kept events
            with open(self.file_path, "w") as f:
                for line in kept_events:
                    f.write(line)

            logger.info(f"Cleaned up {deleted_count} old audit events")

        except Exception as e:
            logger.error(f"Failed to cleanup old audit events: {e}")

        return deleted_count

    async def get_event_by_id(self, event_id: str) -> Optional[Dict[str, Any]]:
        """Retrieve a specific audit event by ID."""
        try:
            with open(self.file_path, "r") as f:
                for line in f:
                    if not line.strip():
                        continue

                    event = json.loads(line)
                    if event["id"] == event_id:
                        event["timestamp"] = datetime.fromisoformat(event["timestamp"])
                        return event

        except Exception as e:
            logger.error(f"Failed to retrieve audit event: {e}")

        return None


# TODO: Add PostgreSQLAuditStore for production use
# TODO: Add ElasticsearchAuditStore for advanced search/analytics
