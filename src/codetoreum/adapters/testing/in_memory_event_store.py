"""In-memory event store for testing."""

import asyncio
from datetime import datetime, timezone
from typing import Any, AsyncIterator, Dict, List, Optional
from uuid import UUID

from codetoreum.domain.events import DomainEvent
from codetoreum.ports.exceptions import (
    ConcurrencyConflictError,
    ResourceNotFoundError,
)
from codetoreum.ports.output.event_store import IEventStore


class InMemoryEventStore(IEventStore):
    """
    In-memory event store implementation for testing.

    Uses simple list-based event storage. Supports replay for testing
    and provides complete event history without external dependencies.
    """

    def __init__(self):
        """Initialize the in-memory event store."""
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

    async def append(
        self,
        stream_id: str,
        events: List[DomainEvent],
        expected_version: Optional[int] = None,
    ) -> None:
        """Append events to a stream."""
        if not events:
            return

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
        """Get events from a stream."""
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
        """Get events since a timestamp."""
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
        """Stream events in real-time."""
        if stream_id:
            if stream_id not in self._streams:
                raise ResourceNotFoundError("Stream", stream_id)
            events = self._streams[stream_id][from_version:]
        else:
            events = self._all_events[from_version:]

        for event in events:
            await asyncio.sleep(0.001)  # Simulate streaming delay
            yield event

    async def get_stream_version(self, stream_id: str) -> int:
        """Get current version of a stream."""
        if stream_id not in self._streams:
            return 0
        return len(self._streams[stream_id])

    async def stream_exists(self, stream_id: str) -> bool:
        """Check if a stream exists."""
        return stream_id in self._streams

    async def save_snapshot(
        self,
        stream_id: str,
        version: int,
        snapshot: Dict[str, Any],
    ) -> None:
        """Save a snapshot for faster replay."""
        self._snapshots[stream_id] = {
            "version": version,
            "data": snapshot,
            "timestamp": datetime.now(timezone.utc),
        }

    async def get_latest_snapshot(
        self,
        stream_id: str,
    ) -> Optional[Dict[str, Any]]:
        """Get most recent snapshot."""
        return self._snapshots.get(stream_id)

    async def delete_stream(self, stream_id: str) -> None:
        """Delete an event stream."""
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
        """Get all stream IDs."""
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
        """Get events by event type."""
        events = self._events_by_type.get(event_type, [])

        if since:
            events = [e for e in events if e.occurred_at > since]

        return events[:limit]

    async def get_events_by_correlation_id(
        self,
        correlation_id: str,
    ) -> List[DomainEvent]:
        """Get all events with a specific correlation ID."""
        return self._events_by_correlation.get(correlation_id, []).copy()

    async def replay_events(
        self,
        stream_id: str,
        from_version: int = 0,
        to_version: Optional[int] = None,
    ) -> AsyncIterator[DomainEvent]:
        """Replay events from a stream for debugging/recovery."""
        if stream_id not in self._streams:
            raise ResourceNotFoundError("Stream", stream_id)

        events = self._streams[stream_id]

        # Apply version filters
        if to_version is not None:
            events = events[from_version:to_version + 1]
        else:
            events = events[from_version:]

        for event in events:
            await asyncio.sleep(0.001)  # Simulate replay delay
            yield event

    async def get_statistics(self) -> Dict[str, Any]:
        """Get event store statistics."""
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
        """Clear all events and streams."""
        self._streams.clear()
        self._snapshots.clear()
        self._all_events.clear()
        self._events_by_type.clear()
        self._events_by_correlation.clear()

    def get_total_event_count(self) -> int:
        """Get total number of events across all streams."""
        return len(self._all_events)

    def get_stream_count(self) -> int:
        """Get number of streams."""
        return len(self._streams)

    def get_events_for_stream(self, stream_id: str) -> List[DomainEvent]:
        """Get all events for a stream (synchronous, for testing)."""
        return self._streams.get(stream_id, []).copy()

    def get_all_events_list(self) -> List[DomainEvent]:
        """Get all events across all streams (for testing)."""
        return self._all_events.copy()
