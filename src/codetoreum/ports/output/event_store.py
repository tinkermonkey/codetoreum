"""IEventStore output port interface."""

from abc import ABC, abstractmethod
from datetime import datetime
from typing import Any, AsyncIterator, Dict, List, Optional

from codetoreum.domain.events import DomainEvent
from codetoreum.domain.types import CorrelationId, EventId, StreamId

# ============================================================================
# Port Interface
# ============================================================================


class IEventStore(ABC):
    """Interface for event sourcing and persistence."""

    @abstractmethod
    async def append(
        self,
        stream_id: str,
        events: List[DomainEvent],
        expected_version: Optional[int] = None,
    ) -> None:
        """
        Append events to a stream.

        Args:
            stream_id: Event stream identifier (e.g., aggregate ID)
            events: Events to append
            expected_version: Expected current version for optimistic concurrency

        Raises:
            ConcurrencyConflictError: Version mismatch
            EventStoreError: Persistence failure
        """
        pass

    @abstractmethod
    async def get_events(
        self,
        stream_id: str,
        from_version: int = 0,
        to_version: Optional[int] = None,
    ) -> List[DomainEvent]:
        """
        Get events from a stream.

        Args:
            stream_id: Event stream identifier
            from_version: Start from this version (inclusive)
            to_version: End at this version (inclusive), or None for all

        Returns:
            List[DomainEvent]: List of events in order

        Raises:
            ResourceNotFoundError: Stream doesn't exist
            EventStoreError: Retrieval failure
        """
        pass

    @abstractmethod
    async def get_events_since(
        self,
        since: datetime,
        stream_id: Optional[str] = None,
    ) -> List[DomainEvent]:
        """
        Get events since a timestamp.

        Args:
            since: Return events after this timestamp
            stream_id: Optional stream filter

        Returns:
            List[DomainEvent]: List of events

        Raises:
            EventStoreError: Retrieval failure
        """
        pass

    @abstractmethod
    async def stream_events(
        self,
        stream_id: Optional[str] = None,
        from_version: int = 0,
    ) -> AsyncIterator[DomainEvent]:
        """
        Stream events in real-time.

        Args:
            stream_id: Optional stream filter
            from_version: Start from this version

        Yields:
            DomainEvent: Events as they are appended

        Raises:
            EventStoreError: Streaming failure
        """
        pass

    @abstractmethod
    async def get_stream_version(self, stream_id: str) -> int:
        """
        Get current version of a stream.

        Args:
            stream_id: Event stream identifier

        Returns:
            int: Current version (0 if stream doesn't exist)

        Raises:
            EventStoreError: Query failure
        """
        pass

    @abstractmethod
    async def stream_exists(self, stream_id: str) -> bool:
        """
        Check if a stream exists.

        Args:
            stream_id: Event stream identifier

        Returns:
            bool: True if stream exists

        Raises:
            EventStoreError: Query failure
        """
        pass

    @abstractmethod
    async def save_snapshot(
        self,
        stream_id: str,
        version: int,
        snapshot: Dict[str, Any],
    ) -> None:
        """
        Save a snapshot for faster replay.

        Args:
            stream_id: Event stream identifier
            version: Stream version at snapshot time
            snapshot: Snapshot data

        Raises:
            EventStoreError: Snapshot save failure
        """
        pass

    @abstractmethod
    async def get_latest_snapshot(
        self,
        stream_id: str,
    ) -> Optional[Dict[str, Any]]:
        """
        Get most recent snapshot.

        Args:
            stream_id: Event stream identifier

        Returns:
            Optional[Dict[str, Any]]: Snapshot data or None if no snapshot exists

        Raises:
            EventStoreError: Snapshot retrieval failure
        """
        pass

    @abstractmethod
    async def delete_stream(self, stream_id: str) -> None:
        """
        Delete an event stream.

        Args:
            stream_id: Event stream identifier

        Raises:
            ResourceNotFoundError: Stream doesn't exist
            EventStoreError: Delete operation failed
        """
        pass

    @abstractmethod
    async def get_all_stream_ids(
        self,
        aggregate_type: Optional[str] = None,
    ) -> List[str]:
        """
        Get all stream IDs.

        Args:
            aggregate_type: Optional filter by aggregate type

        Returns:
            List[str]: List of stream IDs

        Raises:
            EventStoreError: Query failure
        """
        pass

    @abstractmethod
    async def get_events_by_type(
        self,
        event_type: str,
        since: Optional[datetime] = None,
        limit: int = 1000,
    ) -> List[DomainEvent]:
        """
        Get events by event type.

        Args:
            event_type: Event type name
            since: Optional timestamp filter
            limit: Maximum number of events to return

        Returns:
            List[DomainEvent]: List of matching events

        Raises:
            EventStoreError: Query failure
        """
        pass

    @abstractmethod
    async def get_events_by_correlation_id(
        self,
        correlation_id: str,
    ) -> List[DomainEvent]:
        """
        Get all events with a specific correlation ID.

        Args:
            correlation_id: Correlation ID to search for

        Returns:
            List[DomainEvent]: List of correlated events

        Raises:
            EventStoreError: Query failure
        """
        pass

    @abstractmethod
    async def replay_events(
        self,
        stream_id: str,
        from_version: int = 0,
        to_version: Optional[int] = None,
    ) -> AsyncIterator[DomainEvent]:
        """
        Replay events from a stream for debugging/recovery.

        Args:
            stream_id: Event stream identifier
            from_version: Start from this version
            to_version: End at this version (None for all)

        Yields:
            DomainEvent: Events in order

        Raises:
            ResourceNotFoundError: Stream doesn't exist
            EventStoreError: Replay failure
        """
        pass

    @abstractmethod
    async def get_statistics(self) -> Dict[str, Any]:
        """
        Get event store statistics.

        Returns:
            Dict[str, Any]: Statistics (total events, streams, etc.)

        Raises:
            EventStoreError: Query failure
        """
        pass
