"""In-memory event store for testing."""

import asyncio
import threading
from datetime import datetime, timezone
from typing import Any, AsyncIterator, Dict, List, Optional
from uuid import UUID

from codetoreum.domain.events import DomainEvent
from codetoreum.ports.exceptions import (
    ConcurrencyConflictError,
    ResourceNotFoundError,
    ValidationError,
)
from codetoreum.ports.output.event_store import IEventStore


class InMemoryEventStore(IEventStore):
    """
    In-memory event store implementation for testing.

    Uses simple list-based event storage. Supports replay for testing
    and provides complete event history without external dependencies.

    Note: This adapter is thread-safe for concurrent test execution. All
    dictionary and list modifications are protected by a lock.
    """

    def __init__(self):
        """Initialize the in-memory event store with thread-safe storage."""
        # Stream storage: stream_id -> list of events
        self._streams: Dict[str, List[DomainEvent]] = {}

        # Snapshot storage: stream_id -> snapshot data
        self._snapshots: Dict[str, Dict[str, Any]] = {}

        # Global event list for cross-stream queries
        self._all_events: List[DomainEvent] = []

        # Event type index for fast lookups
        self._events_by_type: Dict[str, List[DomainEvent]] = {}

        # Correlation ID index
        self._events_by_correlation: Dict[str, List[DomainEvent]] = {}

        # Thread safety for concurrent test execution
        self._lock = threading.Lock()

    async def append(
        self,
        stream_id: str,
        events: List[DomainEvent],
        expected_version: Optional[int] = None,
    ) -> None:
        """
        Append events to a stream.

        Args:
            stream_id: Unique stream identifier
            events: List of domain events to append
            expected_version: Optional expected version for optimistic concurrency control

        Raises:
            ConcurrencyConflictError: If expected_version doesn't match current version
            ValidationError: If stream_id is None/empty
        """
        if not stream_id:
            raise ValidationError("Stream ID cannot be empty")

        if not events:
            return

        with self._lock:
            # Check version for optimistic concurrency control
            if expected_version is not None:
                current_version = len(self._streams.get(stream_id, []))
                if current_version != expected_version:
                    raise ConcurrencyConflictError(
                        f"Expected version {expected_version}, but stream is at version {current_version}"
                    )

            # Initialize stream if it doesn't exist
            if stream_id not in self._streams:
                self._streams[stream_id] = []

            # Append events
            for event in events:
                self._streams[stream_id].append(event)
                self._all_events.append(event)

                # Update indexes
                event_type = event.event_type
                if event_type not in self._events_by_type:
                    self._events_by_type[event_type] = []
                self._events_by_type[event_type].append(event)

                # Index by correlation ID
                if event.correlation_id:
                    corr_id = str(event.correlation_id)
                    if corr_id not in self._events_by_correlation:
                        self._events_by_correlation[corr_id] = []
                    self._events_by_correlation[corr_id].append(event)

    async def get_events(
        self,
        stream_id: str,
        from_version: int = 0,
        to_version: Optional[int] = None,
    ) -> List[DomainEvent]:
        """
        Get events from a stream.

        Args:
            stream_id: Unique stream identifier
            from_version: Starting version (inclusive, default 0)
            to_version: Optional ending version (inclusive)

        Returns:
            List of domain events

        Raises:
            ResourceNotFoundError: If stream doesn't exist
            ValidationError: If stream_id is None/empty
        """
        if not stream_id:
            raise ValidationError("Stream ID cannot be empty")

        with self._lock:
            if stream_id not in self._streams:
                raise ResourceNotFoundError("Stream", stream_id)

            events = self._streams[stream_id]

            # Apply version filters
            if to_version is not None:
                events = events[from_version:to_version + 1]
            else:
                events = events[from_version:]

            return events.copy()

    async def get_events_since(
        self,
        since: datetime,
        stream_id: Optional[str] = None,
    ) -> List[DomainEvent]:
        """
        Get events since a timestamp.

        Args:
            since: Timestamp to filter events after
            stream_id: Optional stream ID to filter by

        Returns:
            List of domain events after the given timestamp

        Raises:
            ValidationError: If since is None
        """
        if not since:
            raise ValidationError("Since timestamp cannot be None")

        with self._lock:
            if stream_id:
                if stream_id not in self._streams:
                    return []
                events = self._streams[stream_id]
            else:
                events = self._all_events

            return [e for e in events if e.occurred_at > since]

    async def stream_events(
        self,
        stream_id: Optional[str] = None,
        from_version: int = 0,
    ) -> AsyncIterator[DomainEvent]:
        """
        Stream events in real-time.

        Args:
            stream_id: Optional stream ID to filter by
            from_version: Starting version (default 0)

        Yields:
            Domain events

        Raises:
            ResourceNotFoundError: If stream doesn't exist
        """
        with self._lock:
            if stream_id:
                if stream_id not in self._streams:
                    raise ResourceNotFoundError("Stream", stream_id)
                events = self._streams[stream_id][from_version:].copy()
            else:
                events = self._all_events[from_version:].copy()

        for event in events:
            await asyncio.sleep(0.001)  # Simulate streaming delay
            yield event

    async def get_stream_version(self, stream_id: str) -> int:
        """
        Get current version of a stream.

        Args:
            stream_id: Unique stream identifier

        Returns:
            Stream version (0 if stream doesn't exist)

        Raises:
            ValidationError: If stream_id is None/empty
        """
        if not stream_id:
            raise ValidationError("Stream ID cannot be empty")

        with self._lock:
            if stream_id not in self._streams:
                return 0
            return len(self._streams[stream_id])

    async def stream_exists(self, stream_id: str) -> bool:
        """
        Check if a stream exists.

        Args:
            stream_id: Unique stream identifier

        Returns:
            True if stream exists, False otherwise

        Raises:
            ValidationError: If stream_id is None/empty
        """
        if not stream_id:
            raise ValidationError("Stream ID cannot be empty")

        with self._lock:
            return stream_id in self._streams

    async def save_snapshot(
        self,
        stream_id: str,
        version: int,
        snapshot: Dict[str, Any],
    ) -> None:
        """
        Save a snapshot for faster replay.

        Args:
            stream_id: Unique stream identifier
            version: Stream version at snapshot
            snapshot: Snapshot data dictionary

        Raises:
            ValidationError: If stream_id or snapshot is None/empty
        """
        if not stream_id:
            raise ValidationError("Stream ID cannot be empty")

        if snapshot is None:
            raise ValidationError("Snapshot data cannot be None")

        with self._lock:
            self._snapshots[stream_id] = {
                "version": version,
                "data": snapshot,
                "timestamp": datetime.now(timezone.utc),
            }

    async def get_latest_snapshot(
        self,
        stream_id: str,
    ) -> Optional[Dict[str, Any]]:
        """
        Get most recent snapshot.

        Args:
            stream_id: Unique stream identifier

        Returns:
            Snapshot data dictionary or None if no snapshot exists

        Raises:
            ValidationError: If stream_id is None/empty
        """
        if not stream_id:
            raise ValidationError("Stream ID cannot be empty")

        with self._lock:
            return self._snapshots.get(stream_id)

    async def delete_stream(self, stream_id: str) -> None:
        """
        Delete an event stream.

        Args:
            stream_id: Unique stream identifier

        Raises:
            ResourceNotFoundError: If stream doesn't exist
            ValidationError: If stream_id is None/empty
        """
        if not stream_id:
            raise ValidationError("Stream ID cannot be empty")

        with self._lock:
            if stream_id not in self._streams:
                raise ResourceNotFoundError("Stream", stream_id)

            # Remove from streams
            events_to_remove = self._streams[stream_id]
            del self._streams[stream_id]

            # Remove from global events list
            for event in events_to_remove:
                if event in self._all_events:
                    self._all_events.remove(event)

                # Remove from type index
                event_type = event.event_type
                if event_type in self._events_by_type:
                    if event in self._events_by_type[event_type]:
                        self._events_by_type[event_type].remove(event)

                # Remove from correlation index
                if event.correlation_id:
                    corr_id = str(event.correlation_id)
                    if corr_id in self._events_by_correlation:
                        if event in self._events_by_correlation[corr_id]:
                            self._events_by_correlation[corr_id].remove(event)

            # Remove snapshot
            if stream_id in self._snapshots:
                del self._snapshots[stream_id]

    async def get_all_stream_ids(
        self,
        aggregate_type: Optional[str] = None,
    ) -> List[str]:
        """
        Get all stream IDs.

        Args:
            aggregate_type: Optional aggregate type to filter by

        Returns:
            List of stream IDs
        """
        with self._lock:
            if aggregate_type:
                # Filter by aggregate type
                stream_ids = []
                for stream_id, events in self._streams.items():
                    if events and events[0].aggregate_type == aggregate_type:
                        stream_ids.append(stream_id)
                return stream_ids

            return list(self._streams.keys())

    async def get_events_by_type(
        self,
        event_type: str,
        since: Optional[datetime] = None,
        limit: int = 1000,
    ) -> List[DomainEvent]:
        """
        Get events by event type.

        Args:
            event_type: Event type to filter by
            since: Optional timestamp to filter events after
            limit: Maximum number of events to return (default 1000)

        Returns:
            List of domain events

        Raises:
            ValidationError: If event_type is None/empty
        """
        if not event_type:
            raise ValidationError("Event type cannot be empty")

        with self._lock:
            events = self._events_by_type.get(event_type, [])

            if since:
                events = [e for e in events if e.occurred_at > since]

            return events[:limit]

    async def get_events_by_correlation_id(
        self,
        correlation_id: str,
    ) -> List[DomainEvent]:
        """
        Get all events with a specific correlation ID.

        Args:
            correlation_id: Correlation ID to filter by

        Returns:
            List of domain events

        Raises:
            ValidationError: If correlation_id is None/empty
        """
        if not correlation_id:
            raise ValidationError("Correlation ID cannot be empty")

        with self._lock:
            return self._events_by_correlation.get(correlation_id, []).copy()

    async def replay_events(
        self,
        stream_id: str,
        from_version: int = 0,
        to_version: Optional[int] = None,
    ) -> AsyncIterator[DomainEvent]:
        """
        Replay events from a stream for debugging/recovery.

        Args:
            stream_id: Unique stream identifier
            from_version: Starting version (default 0)
            to_version: Optional ending version

        Yields:
            Domain events

        Raises:
            ResourceNotFoundError: If stream doesn't exist
            ValidationError: If stream_id is None/empty
        """
        if not stream_id:
            raise ValidationError("Stream ID cannot be empty")

        with self._lock:
            if stream_id not in self._streams:
                raise ResourceNotFoundError("Stream", stream_id)

            events = self._streams[stream_id]

            # Apply version filters
            if to_version is not None:
                events = events[from_version:to_version + 1]
            else:
                events = events[from_version:]

            # Copy to avoid holding lock during iteration
            events = events.copy()

        for event in events:
            await asyncio.sleep(0.001)  # Simulate replay delay
            yield event

    async def get_statistics(self) -> Dict[str, Any]:
        """
        Get event store statistics.

        Returns:
            Dictionary with event store statistics
        """
        with self._lock:
            total_events = len(self._all_events)
            total_streams = len(self._streams)

            # Calculate events per stream
            events_per_stream = {}
            for stream_id, events in self._streams.items():
                events_per_stream[stream_id] = len(events)

            # Calculate events per type
            events_per_type = {}
            for event_type, events in self._events_by_type.items():
                events_per_type[event_type] = len(events)

            return {
                "total_events": total_events,
                "total_streams": total_streams,
                "total_snapshots": len(self._snapshots),
                "events_per_stream": events_per_stream,
                "events_per_type": events_per_type,
                "unique_event_types": len(self._events_by_type),
                "unique_correlation_ids": len(self._events_by_correlation),
            }

    # Helper methods for testing

    def clear(self) -> None:
        """
        Clear all events and streams.

        This is a testing helper method to reset the adapter state.
        """
        with self._lock:
            self._streams.clear()
            self._snapshots.clear()
            self._all_events.clear()
            self._events_by_type.clear()
            self._events_by_correlation.clear()

    def get_total_event_count(self) -> int:
        """
        Get total number of events across all streams.

        Returns:
            Total event count
        """
        with self._lock:
            return len(self._all_events)

    def get_stream_count(self) -> int:
        """
        Get number of streams.

        Returns:
            Number of streams
        """
        with self._lock:
            return len(self._streams)

    def get_events_for_stream(self, stream_id: str) -> List[DomainEvent]:
        """
        Get all events for a stream (synchronous, for testing).

        Args:
            stream_id: Unique stream identifier

        Returns:
            List of domain events
        """
        with self._lock:
            return self._streams.get(stream_id, []).copy()

    def get_all_events_list(self) -> List[DomainEvent]:
        """
        Get all events across all streams (for testing).

        Returns:
            List of all domain events
        """
        with self._lock:
            return self._all_events.copy()
