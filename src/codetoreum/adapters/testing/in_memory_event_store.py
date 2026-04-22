"""In-memory event store for testing."""

import asyncio
import random
import threading
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from codetoreum.domain.events import DomainEvent
from codetoreum.ports.exceptions import (
    ConcurrencyConflictError,
    ResourceNotFoundError,
    ValidationError,
)
from codetoreum.ports.output.event_store import IEventStore

if TYPE_CHECKING:
    from codetoreum.infrastructure.simulation.simulation_config import (
        SimulationConfig,
    )


class InMemoryEventStore(IEventStore):
    """
    In-memory event store implementation for testing.

    Uses simple list-based event storage. Supports replay for testing
    and provides complete event history without external dependencies.

    Supports fidelity-aware timing when SimulationConfig is provided:
    - LOW: no delay
    - MEDIUM: uses ms_per_event from config
    - HIGH: uses ms_per_event with ±20% jitter

    Note: This adapter is thread-safe for concurrent test execution. All
    dictionary and list modifications are protected by a lock.
    """

    def __init__(
        self,
        config: "SimulationConfig | None" = None,
        clock: "Any | None" = None,
    ):
        """
        Initialize the in-memory event store with thread-safe storage.

        Args:
            config: Optional SimulationConfig for fidelity-aware timing
            clock: Optional SimulationClock for time manipulation
        """
        # Stream storage: stream_id -> list of events
        self._streams: dict[str, list[DomainEvent]] = {}

        # Snapshot storage: stream_id -> snapshot data
        self._snapshots: dict[str, dict[str, Any]] = {}

        # Global event list for cross-stream queries
        self._all_events: list[DomainEvent] = []

        # Event type index for fast lookups
        self._events_by_type: dict[str, list[DomainEvent]] = {}

        # Correlation ID index
        self._events_by_correlation: dict[str, list[DomainEvent]] = {}

        # Thread safety for concurrent test execution
        self._lock = threading.Lock()

        # Configuration for fidelity-aware timing
        self._config = config
        self._clock = clock

    async def append(
        self,
        stream_id: str,
        events: list[DomainEvent],
        expected_version: int | None = None,
    ) -> None:
        """
        Append events to a stream with spec-compliant processing latency.

        Implements the event store timing model (US-3.3):
        Latency = event_count * handler_count * ms_per_event

        Example: Appending 1000 events with 5 handlers and 1ms per unit = 5 seconds latency

        Latency components:
        - event_count: Number of events being appended
        - handler_count: Number of event handlers (SimulationConfig.event_handler_count)
        - ms_per_event: Processing delay per unit (SimulationConfig.ms_per_event)
        - Fidelity level: Affects whether delay is applied (LOW: no delay, MEDIUM/HIGH: with delay)

        This backpressure mechanism ensures that appending many events incurs proportional
        delays, accurately modeling real event processing costs.

        Args:
            stream_id: Unique stream identifier
            events: List of domain events to append
            expected_version: Optional expected version for optimistic concurrency control

        Raises:
            ConcurrencyConflictError: If expected_version doesn't match current version
            ValidationError: If stream_id is None/empty
        """
        if not stream_id:
            msg = "Stream ID cannot be empty"
            raise ValidationError(msg)

        if not events:
            return

        with self._lock:
            # Check version for optimistic concurrency control
            if expected_version is not None:
                current_version = len(self._streams.get(stream_id, []))
                if current_version != expected_version:
                    msg = f"Expected version {expected_version}, but stream is at version {current_version}"
                    raise ConcurrencyConflictError(msg)

            # Initialize stream if it doesn't exist
            if stream_id not in self._streams:
                self._streams[stream_id] = []

            # Append events
            for event in events:
                self._streams[stream_id].append(event)
                self._all_events.append(event)

                # Update indexes
                # Handle both old DomainEvent (event_type) and new CodetoreumEvent (type)
                event_type = getattr(event, "event_type", None) or getattr(event, "type", None)
                if event_type:
                    if event_type not in self._events_by_type:
                        self._events_by_type[event_type] = []
                    self._events_by_type[event_type].append(event)

                # Index by correlation ID
                if event.correlation_id:
                    corr_id = str(event.correlation_id)
                    if corr_id not in self._events_by_correlation:
                        self._events_by_correlation[corr_id] = []
                    self._events_by_correlation[corr_id].append(event)

        # Apply backpressure: simulate event processing latency (outside of lock)
        # This represents the cost of event handlers processing the appended events
        await self._apply_event_processing_latency(len(events))

    async def get_events(
        self,
        stream_id: str,
        from_version: int = 0,
        to_version: int | None = None,
    ) -> list[DomainEvent]:
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
            msg = "Stream ID cannot be empty"
            raise ValidationError(msg)

        with self._lock:
            if stream_id not in self._streams:
                msg = "Stream"
                raise ResourceNotFoundError(msg, stream_id)

            events = self._streams[stream_id]

            # Apply version filters
            if to_version is not None:
                events = events[from_version : to_version + 1]
            else:
                events = events[from_version:]

            return events.copy()

    async def get_events_since(
        self,
        since: datetime,
        stream_id: str | None = None,
    ) -> list[DomainEvent]:
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
            msg = "Since timestamp cannot be None"
            raise ValidationError(msg)

        with self._lock:
            if stream_id:
                if stream_id not in self._streams:
                    return []
                events = self._streams[stream_id]
            else:
                events = self._all_events

            return [e for e in events if e.occurred_at > since]

    async def _get_event_delay_seconds(self) -> float:
        """
        Calculate base delay per (event * handler) unit.

        This is the unit latency that will be multiplied by both event_count and handler_count
        in the full latency formula: latency = event_count * handler_count * delay_per_unit

        Uses fidelity-aware timing from SimulationConfig if available.
        - LOW: 0 delay
        - MEDIUM: ms_per_event from config (e.g., 1ms per unit)
        - HIGH: ms_per_event with ±20% jitter

        Returns:
            Delay in seconds per (event * handler) unit
        """
        if not self._config:
            # Default behavior (for backward compatibility)
            return 0.001

        # Import at runtime to respect TYPE_CHECKING guard
        from codetoreum.infrastructure.simulation.simulation_config import FidelityLevel

        if self._config.fidelity_level == FidelityLevel.LOW:
            return 0.0

        # MEDIUM/HIGH: use ms_per_event from config
        delay_seconds = self._config.ms_per_event / 1000.0

        # HIGH fidelity: add timing jitter (±20% randomness)
        if self._config.fidelity_level == FidelityLevel.HIGH:
            delay_seconds = random.uniform(delay_seconds * 0.8, delay_seconds * 1.2)

        return delay_seconds

    async def _apply_event_processing_latency(self, event_count: int) -> None:
        """
        Apply backpressure latency for event processing.

        Implements the event store timing model per specification (US-3.3):
        Latency = event_count * handler_count * ms_per_event

        Example: 1000 events * 5 handlers * 1ms = 5 seconds

        This is the **backpressure mechanism** that ensures appending many
        events incurs proportional delays, matching real event processing costs.
        The formula accounts for all event handlers that process the events.

        Args:
            event_count: Number of events being processed
        """
        if not self._config or event_count == 0:
            return

        # Get per-event delay (handles fidelity level and jitter)
        delay_per_event = await self._get_event_delay_seconds()

        # Apply spec-compliant formula: total = event_count * handler_count * delay_per_event
        handler_count = self._config.event_handler_count
        total_delay_seconds = delay_per_event * event_count * handler_count

        if total_delay_seconds > 0:
            if self._clock:
                # Use simulated clock for time manipulation
                await self._clock.sleep(total_delay_seconds)
            else:
                # Fall back to asyncio.sleep
                await asyncio.sleep(total_delay_seconds)

    async def stream_events(
        self,
        stream_id: str | None = None,
        from_version: int = 0,
    ) -> AsyncIterator[DomainEvent]:
        """
        Stream events in real-time.

        Uses fidelity-aware timing when SimulationConfig is provided.

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
                    msg = "Stream"
                    raise ResourceNotFoundError(msg, stream_id)
                events = self._streams[stream_id][from_version:].copy()
            else:
                events = self._all_events[from_version:].copy()

        delay_seconds = await self._get_event_delay_seconds()
        # Multiply by handler count per spec: latency = event_count * handler_count * ms_per_event
        handler_count = self._config.event_handler_count if self._config else 1
        delay_with_handlers = delay_seconds * handler_count

        for event in events:
            if delay_with_handlers > 0:
                if self._clock:
                    # Use simulated clock for time manipulation
                    await self._clock.sleep(delay_with_handlers)
                else:
                    # Fall back to asyncio.sleep
                    await asyncio.sleep(delay_with_handlers)
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
            msg = "Stream ID cannot be empty"
            raise ValidationError(msg)

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
            msg = "Stream ID cannot be empty"
            raise ValidationError(msg)

        with self._lock:
            return stream_id in self._streams

    async def save_snapshot(
        self,
        stream_id: str,
        version: int,
        snapshot: dict[str, Any],
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
            msg = "Stream ID cannot be empty"
            raise ValidationError(msg)

        if snapshot is None:
            msg = "Snapshot data cannot be None"
            raise ValidationError(msg)

        with self._lock:
            self._snapshots[stream_id] = {
                "version": version,
                "data": snapshot,
                "timestamp": datetime.now(UTC),
            }

    async def get_latest_snapshot(
        self,
        stream_id: str,
    ) -> dict[str, Any] | None:
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
            msg = "Stream ID cannot be empty"
            raise ValidationError(msg)

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
            msg = "Stream ID cannot be empty"
            raise ValidationError(msg)

        with self._lock:
            if stream_id not in self._streams:
                msg = "Stream"
                raise ResourceNotFoundError(msg, stream_id)

            # Remove from streams
            events_to_remove = self._streams[stream_id]
            del self._streams[stream_id]

            # Remove from global events list
            for event in events_to_remove:
                if event in self._all_events:
                    self._all_events.remove(event)

                # Remove from type index
                # Handle both old DomainEvent (event_type) and new CodetoreumEvent (type)
                event_type = getattr(event, "event_type", None) or getattr(event, "type", None)
                if event_type and event_type in self._events_by_type:
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
        aggregate_type: str | None = None,
    ) -> list[str]:
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
        since: datetime | None = None,
        limit: int = 1000,
    ) -> list[DomainEvent]:
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
            msg = "Event type cannot be empty"
            raise ValidationError(msg)

        with self._lock:
            events = self._events_by_type.get(event_type, [])

            if since:
                events = [e for e in events if e.occurred_at > since]

            return events[:limit]

    async def get_events_by_correlation_id(
        self,
        correlation_id: str,
    ) -> list[DomainEvent]:
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
            msg = "Correlation ID cannot be empty"
            raise ValidationError(msg)

        with self._lock:
            return self._events_by_correlation.get(correlation_id, []).copy()

    async def replay_events(
        self,
        stream_id: str,
        from_version: int = 0,
        to_version: int | None = None,
    ) -> AsyncIterator[DomainEvent]:
        """
        Replay events from a stream for debugging/recovery.

        Uses fidelity-aware timing when SimulationConfig is provided.

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
            msg = "Stream ID cannot be empty"
            raise ValidationError(msg)

        with self._lock:
            if stream_id not in self._streams:
                msg = "Stream"
                raise ResourceNotFoundError(msg, stream_id)

            events = self._streams[stream_id]

            # Apply version filters
            if to_version is not None:
                events = events[from_version : to_version + 1]
            else:
                events = events[from_version:]

            # Copy to avoid holding lock during iteration
            events = events.copy()

        delay_seconds = await self._get_event_delay_seconds()
        # Multiply by handler count per spec: latency = event_count * handler_count * ms_per_event
        handler_count = self._config.event_handler_count if self._config else 1
        delay_with_handlers = delay_seconds * handler_count

        for event in events:
            if delay_with_handlers > 0:
                if self._clock:
                    # Use simulated clock for time manipulation
                    await self._clock.sleep(delay_with_handlers)
                else:
                    # Fall back to asyncio.sleep
                    await asyncio.sleep(delay_with_handlers)
            yield event

    async def get_statistics(self) -> dict[str, Any]:
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

    def get_events_for_stream(self, stream_id: str) -> list[DomainEvent]:
        """
        Get all events for a stream (synchronous, for testing).

        Args:
            stream_id: Unique stream identifier

        Returns:
            List of domain events
        """
        with self._lock:
            return self._streams.get(stream_id, []).copy()

    def get_all_events_list(self) -> list[DomainEvent]:
        """
        Get all events across all streams (for testing).

        Returns:
            List of all domain events
        """
        with self._lock:
            return self._all_events.copy()

    @property
    def events(self) -> list[DomainEvent]:
        """
        Get all events across all streams (property for convenient test access).

        Returns:
            List of all domain events
        """
        return self.get_all_events_list()

    async def query_streams_by_latest_event(
        self,
        aggregate_type: str,
        event_type_filters: list[str] | None = None,
        event_data_filters: dict[str, Any] | None = None,
        sort_by: str = "timestamp",
        sort_order: str = "desc",
        offset: int = 0,
        limit: int = 100,
    ) -> tuple[list[str], int]:
        """
        Query stream IDs by analyzing their latest events with in-memory filtering.

        This is a simplified in-memory implementation for testing purposes.
        For production use, see ElasticsearchEventStore which uses database-level
        aggregations for better performance.

        Args:
            aggregate_type: Filter by aggregate type (e.g., "Workflow")
            event_type_filters: Optional list of event types to filter by
            event_data_filters: Optional filters on event data fields
            sort_by: Field to sort by (timestamp, stream_version, etc.)
            sort_order: Sort order ("asc" or "desc")
            offset: Pagination offset
            limit: Maximum number of stream IDs to return

        Returns:
            Tuple of (stream_ids, total_count)

        Raises:
            ValidationError: If parameters are invalid
        """
        if not aggregate_type:
            msg = "Aggregate type cannot be empty"
            raise ValidationError(msg)

        with self._lock:
            # Filter streams by aggregate type
            matching_streams = []

            for stream_id, events in self._streams.items():
                if not events:
                    continue

                # Check if stream matches aggregate type
                if events[0].aggregate_type != aggregate_type:
                    continue

                # Get latest event for this stream
                latest_event = events[-1]

                # Apply event type filters
                # Handle both old DomainEvent (event_type) and new CodetoreumEvent (type)
                if event_type_filters:
                    latest_event_type = getattr(latest_event, "event_type", None) or getattr(latest_event, "type", None)
                    if latest_event_type not in event_type_filters:
                        continue

                # Apply event data filters
                if event_data_filters:
                    matches = True
                    for key, value in event_data_filters.items():
                        # Support nested keys like "data.project_id"
                        if key.startswith("data."):
                            field_name = key[5:]  # Remove "data." prefix
                            # Check across ALL events in the stream, not just latest
                            # (e.g., project_id is in WorkflowCreated event, not necessarily latest)
                            event_value = None
                            for event in events:
                                if field_name in event.payload:
                                    event_value = event.payload[field_name]
                                    break
                        else:
                            event_value = getattr(latest_event, key, None)

                        if event_value != value:
                            matches = False
                            break

                    if not matches:
                        continue

                matching_streams.append((stream_id, latest_event))

            # Sort streams by latest event
            reverse = sort_order == "desc"

            if sort_by == "timestamp":
                matching_streams.sort(key=lambda x: x[1].occurred_at, reverse=reverse)
            elif sort_by == "stream_version":
                matching_streams.sort(key=lambda x: len(self._streams[x[0]]), reverse=reverse)
            else:
                # Default to timestamp
                matching_streams.sort(key=lambda x: x[1].occurred_at, reverse=reverse)

            # Extract stream IDs
            all_stream_ids = [stream_id for stream_id, _ in matching_streams]
            total_count = len(all_stream_ids)

            # Apply pagination
            paginated_stream_ids = all_stream_ids[offset : offset + limit]

            return paginated_stream_ids, total_count
