"""Event replayer service for debugging and recovery."""

import asyncio
import logging
from datetime import datetime, timedelta, timezone
from typing import Any, AsyncIterator, Callable, Dict, List, Optional

from codetoreum.domain.events import DomainEvent
from codetoreum.infrastructure.event_bus import EventBus
from codetoreum.ports.output.event_store import IEventStore

logger = logging.getLogger(__name__)


class EventReplayerError(Exception):
    """Raised when event replay operations fail."""

    pass


class EventReplayer:
    """
    Service for replaying events from event store.

    Use cases:
    - Debugging: Replay events to understand system state changes
    - Recovery: Rebuild read models or projections from events
    - Testing: Replay production events in test environment
    - Time travel: See system state at a specific point in time
    - Analysis: Analyze event sequences for patterns

    Features:
    - Replay events from specific timestamp
    - Replay events for specific aggregate
    - Replay with time manipulation (speed up/slow down)
    - Replay with filtering by event type
    - Replay with progress tracking
    - Dry-run mode (don't execute handlers)
    """

    def __init__(
        self,
        event_store: IEventStore,
        event_bus: Optional[EventBus] = None,
    ):
        """
        Initialize event replayer.

        Args:
            event_store: Event store to replay from
            event_bus: Optional event bus to publish replayed events to
        """
        self.event_store = event_store
        self.event_bus = event_bus

        self._stats = {
            "events_replayed": 0,
            "errors": 0,
            "started_at": None,
            "completed_at": None,
        }

    async def replay_from_timestamp(
        self,
        since: datetime,
        until: Optional[datetime] = None,
        stream_id: Optional[str] = None,
        event_types: Optional[List[str]] = None,
        speed_multiplier: float = 1.0,
        dry_run: bool = False,
        progress_callback: Optional[Callable[[int, int], None]] = None,
    ) -> Dict[str, Any]:
        """
        Replay events from a specific timestamp.

        Args:
            since: Start replaying from this timestamp
            until: Optional end timestamp (None = replay all events)
            stream_id: Optional filter by stream ID
            event_types: Optional filter by event types
            speed_multiplier: Speed multiplier (1.0 = real-time, 10.0 = 10x faster)
            dry_run: If True, don't publish events to event bus
            progress_callback: Optional callback for progress updates

        Returns:
            Dictionary with replay statistics

        Raises:
            EventReplayerError: If replay fails
        """
        self._reset_stats()
        self._stats["started_at"] = datetime.now(timezone.utc)

        try:
            # Get events from event store
            events = await self.event_store.get_events_since(
                since=since,
                stream_id=stream_id,
            )

            # Filter by until timestamp
            if until:
                events = [e for e in events if e.occurred_at <= until]

            # Filter by event types
            if event_types:
                events = [e for e in events if e.event_type in event_types]

            logger.info(
                f"Replaying {len(events)} events from {since.isoformat()} "
                f"(stream_id={stream_id}, speed={speed_multiplier}x, dry_run={dry_run})"
            )

            total_events = len(events)

            # Replay events
            for i, event in enumerate(events):
                # Publish to event bus (unless dry run)
                if not dry_run and self.event_bus:
                    await self.event_bus.publish(event)

                self._stats["events_replayed"] += 1

                # Progress callback
                if progress_callback:
                    progress_callback(i + 1, total_events)

                # Time manipulation: sleep proportional to event spacing
                if i < len(events) - 1 and speed_multiplier > 0:
                    next_event = events[i + 1]
                    time_diff = (
                        next_event.occurred_at - event.occurred_at
                    ).total_seconds()

                    if time_diff > 0:
                        sleep_time = time_diff / speed_multiplier
                        # Cap sleep time to avoid excessive delays
                        sleep_time = min(sleep_time, 1.0)
                        await asyncio.sleep(sleep_time)

            self._stats["completed_at"] = datetime.now(timezone.utc)

            logger.info(f"Replay completed: {self._stats['events_replayed']} events")

            return self.get_statistics()

        except Exception as e:
            self._stats["errors"] += 1
            raise EventReplayerError(f"Failed to replay events: {e}") from e

    async def replay_stream(
        self,
        stream_id: str,
        from_version: int = 0,
        to_version: Optional[int] = None,
        dry_run: bool = False,
        progress_callback: Optional[Callable[[int, int], None]] = None,
    ) -> Dict[str, Any]:
        """
        Replay events for a specific stream (aggregate).

        Args:
            stream_id: Stream ID to replay
            from_version: Start from this version
            to_version: End at this version (None for all)
            dry_run: If True, don't publish events to event bus
            progress_callback: Optional callback for progress updates

        Returns:
            Dictionary with replay statistics

        Raises:
            EventReplayerError: If replay fails
        """
        self._reset_stats()
        self._stats["started_at"] = datetime.now(timezone.utc)

        try:
            # Get events from event store
            events = await self.event_store.get_events(
                stream_id=stream_id,
                from_version=from_version,
                to_version=to_version,
            )

            logger.info(
                f"Replaying stream {stream_id}: {len(events)} events "
                f"(versions {from_version} to {to_version or 'end'})"
            )

            total_events = len(events)

            # Replay events
            for i, event in enumerate(events):
                # Publish to event bus (unless dry run)
                if not dry_run and self.event_bus:
                    await self.event_bus.publish(event)

                self._stats["events_replayed"] += 1

                # Progress callback
                if progress_callback:
                    progress_callback(i + 1, total_events)

            self._stats["completed_at"] = datetime.now(timezone.utc)

            logger.info(f"Stream replay completed: {self._stats['events_replayed']} events")

            return self.get_statistics()

        except Exception as e:
            self._stats["errors"] += 1
            raise EventReplayerError(f"Failed to replay stream: {e}") from e

    async def replay_event_type(
        self,
        event_type: str,
        since: Optional[datetime] = None,
        limit: int = 1000,
        dry_run: bool = False,
    ) -> Dict[str, Any]:
        """
        Replay all events of a specific type.

        Args:
            event_type: Event type to replay
            since: Optional timestamp filter
            limit: Maximum number of events to replay
            dry_run: If True, don't publish events to event bus

        Returns:
            Dictionary with replay statistics

        Raises:
            EventReplayerError: If replay fails
        """
        self._reset_stats()
        self._stats["started_at"] = datetime.now(timezone.utc)

        try:
            # Get events from event store
            events = await self.event_store.get_events_by_type(
                event_type=event_type,
                since=since,
                limit=limit,
            )

            logger.info(f"Replaying {len(events)} events of type '{event_type}'")

            # Replay events
            for event in events:
                # Publish to event bus (unless dry run)
                if not dry_run and self.event_bus:
                    await self.event_bus.publish(event)

                self._stats["events_replayed"] += 1

            self._stats["completed_at"] = datetime.now(timezone.utc)

            logger.info(f"Event type replay completed: {self._stats['events_replayed']} events")

            return self.get_statistics()

        except Exception as e:
            self._stats["errors"] += 1
            raise EventReplayerError(f"Failed to replay event type: {e}") from e

    async def stream_replay_iterator(
        self,
        stream_id: str,
        from_version: int = 0,
        to_version: Optional[int] = None,
    ) -> AsyncIterator[DomainEvent]:
        """
        Stream events for replay (iterator pattern).

        Useful for custom replay logic where caller controls event processing.

        Args:
            stream_id: Stream ID to replay
            from_version: Start from this version
            to_version: End at this version (None for all)

        Yields:
            Domain events in order

        Raises:
            EventReplayerError: If replay fails
        """
        try:
            async for event in self.event_store.replay_events(
                stream_id=stream_id,
                from_version=from_version,
                to_version=to_version,
            ):
                self._stats["events_replayed"] += 1
                yield event

        except Exception as e:
            self._stats["errors"] += 1
            raise EventReplayerError(f"Failed to stream replay: {e}") from e

    async def rebuild_projection(
        self,
        projection_handler: Any,
        since: Optional[datetime] = None,
        stream_id: Optional[str] = None,
        progress_callback: Optional[Callable[[int, int], None]] = None,
    ) -> Dict[str, Any]:
        """
        Rebuild a projection by replaying events.

        Args:
            projection_handler: Handler with handle() method to process events
            since: Optional timestamp to start from
            stream_id: Optional filter by stream ID
            progress_callback: Optional callback for progress updates

        Returns:
            Dictionary with rebuild statistics

        Raises:
            EventReplayerError: If rebuild fails
        """
        self._reset_stats()
        self._stats["started_at"] = datetime.now(timezone.utc)

        try:
            # Get events
            if since:
                events = await self.event_store.get_events_since(
                    since=since,
                    stream_id=stream_id,
                )
            elif stream_id:
                events = await self.event_store.get_events(stream_id=stream_id)
            else:
                # Get all events (could be expensive!)
                logger.warning("Rebuilding projection from ALL events - this may take a while")
                all_stream_ids = await self.event_store.get_all_stream_ids()
                events = []
                for sid in all_stream_ids:
                    stream_events = await self.event_store.get_events(stream_id=sid)
                    events.extend(stream_events)

                # Sort by timestamp
                events.sort(key=lambda e: e.occurred_at)

            logger.info(f"Rebuilding projection with {len(events)} events")

            total_events = len(events)

            # Process events through handler
            for i, event in enumerate(events):
                await projection_handler.handle(event)

                self._stats["events_replayed"] += 1

                # Progress callback
                if progress_callback:
                    progress_callback(i + 1, total_events)

            self._stats["completed_at"] = datetime.now(timezone.utc)

            logger.info(f"Projection rebuild completed: {self._stats['events_replayed']} events")

            return self.get_statistics()

        except Exception as e:
            self._stats["errors"] += 1
            raise EventReplayerError(f"Failed to rebuild projection: {e}") from e

    def get_statistics(self) -> Dict[str, Any]:
        """
        Get replay statistics.

        Returns:
            Dictionary with statistics
        """
        stats = self._stats.copy()

        # Calculate duration
        if stats["started_at"] and stats["completed_at"]:
            duration = (stats["completed_at"] - stats["started_at"]).total_seconds()
            stats["duration_seconds"] = duration

            # Calculate throughput
            if duration > 0:
                stats["events_per_second"] = stats["events_replayed"] / duration
            else:
                stats["events_per_second"] = 0
        else:
            stats["duration_seconds"] = 0
            stats["events_per_second"] = 0

        return stats

    def _reset_stats(self) -> None:
        """Reset statistics."""
        self._stats = {
            "events_replayed": 0,
            "errors": 0,
            "started_at": None,
            "completed_at": None,
        }


class TimeManipulationReplayer(EventReplayer):
    """
    Extended replayer with time manipulation capabilities for testing.

    Allows fast-forward simulation of event sequences with configurable
    time compression (e.g., 100x faster than real-time).
    """

    async def fast_forward_replay(
        self,
        stream_id: str,
        target_timestamp: datetime,
        speed_multiplier: float = 100.0,
    ) -> Dict[str, Any]:
        """
        Replay events up to a target timestamp in fast-forward mode.

        Args:
            stream_id: Stream ID to replay
            target_timestamp: Replay events up to this timestamp
            speed_multiplier: Time compression factor (100.0 = 100x faster)

        Returns:
            Dictionary with replay statistics

        Raises:
            EventReplayerError: If replay fails
        """
        # Get all events for stream
        events = await self.event_store.get_events(stream_id=stream_id)

        # Filter events up to target timestamp
        events = [e for e in events if e.occurred_at <= target_timestamp]

        logger.info(
            f"Fast-forward replay: {len(events)} events up to {target_timestamp.isoformat()} "
            f"at {speed_multiplier}x speed"
        )

        # Replay with time manipulation
        return await self.replay_from_timestamp(
            since=events[0].occurred_at if events else datetime.now(timezone.utc),
            until=target_timestamp,
            stream_id=stream_id,
            speed_multiplier=speed_multiplier,
        )
