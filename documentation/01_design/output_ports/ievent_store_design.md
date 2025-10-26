# IEventStore Output Port Design

## Overview

The `IEventStore` port provides an abstraction for event sourcing and event persistence. All domain events are stored through this port, enabling event replay, audit trails, and debugging capabilities.

## Port Interface

```python
from abc import ABC, abstractmethod
from typing import List, Optional, AsyncIterator
from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

class IEventStore(ABC):
    """Interface for event sourcing and persistence."""

    @abstractmethod
    async def append(self,
                     stream_id: str,
                     events: List['DomainEvent'],
                     expected_version: Optional[int] = None) -> None:
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
    async def get_events(self,
                        stream_id: str,
                        from_version: int = 0,
                        to_version: Optional[int] = None) -> List['DomainEvent']:
        """Get events from a stream."""
        pass

    @abstractmethod
    async def get_events_since(self,
                              since: datetime,
                              stream_id: Optional[str] = None) -> List['DomainEvent']:
        """Get events since a timestamp."""
        pass

    @abstractmethod
    async def stream_events(self,
                           stream_id: Optional[str] = None,
                           from_version: int = 0) -> AsyncIterator['DomainEvent']:
        """Stream events in real-time."""
        pass

    @abstractmethod
    async def get_stream_version(self, stream_id: str) -> int:
        """Get current version of a stream."""
        pass

    @abstractmethod
    async def save_snapshot(self,
                           stream_id: str,
                           version: int,
                           snapshot: Dict[str, Any]) -> None:
        """Save a snapshot for faster replay."""
        pass

    @abstractmethod
    async def get_latest_snapshot(self,
                                  stream_id: str) -> Optional[Dict[str, Any]]:
        """Get most recent snapshot."""
        pass
```

## Data Models

```python
@dataclass
class DomainEvent:
    """Base domain event."""
    event_id: UUID
    stream_id: str
    event_type: str
    version: int
    timestamp: datetime
    data: Dict[str, Any]
    metadata: Dict[str, Any]
```

## Adapter Implementations

### Redis Event Store

```python
class RedisEventStore(IEventStore):
    """Redis Streams-based event store."""

    def __init__(self, redis_client):
        self.redis = redis_client

    async def append(self,
                     stream_id: str,
                     events: List[DomainEvent],
                     expected_version: Optional[int] = None) -> None:
        """Append events using Redis Streams."""
        # Check version if specified
        if expected_version is not None:
            current = await self.get_stream_version(stream_id)
            if current != expected_version:
                raise ConcurrencyConflictError(
                    f"Expected version {expected_version}, got {current}"
                )

        # Append events
        for event in events:
            await self.redis.xadd(
                f"events:{stream_id}",
                {
                    'event_id': str(event.event_id),
                    'event_type': event.event_type,
                    'version': event.version,
                    'timestamp': event.timestamp.isoformat(),
                    'data': json.dumps(event.data),
                    'metadata': json.dumps(event.metadata)
                }
            )
```

### In-Memory Event Store (Testing)

```python
class InMemoryEventStore(IEventStore):
    """In-memory event store for testing."""

    def __init__(self):
        self.streams: Dict[str, List[DomainEvent]] = {}
        self.snapshots: Dict[str, Dict[str, Any]] = {}

    async def append(self,
                     stream_id: str,
                     events: List[DomainEvent],
                     expected_version: Optional[int] = None) -> None:
        """Append to in-memory stream."""
        if stream_id not in self.streams:
            self.streams[stream_id] = []

        if expected_version is not None:
            current = len(self.streams[stream_id])
            if current != expected_version:
                raise ConcurrencyConflictError()

        self.streams[stream_id].extend(events)
```

## Integration Points

### Used By
- Domain Models (for emitting events)
- Application Services (for event-driven workflows)
- Event Processors (for consuming events)

### Dependencies
- None (standalone port)

## Implementation Notes

1. **Immutability**: Events are append-only, never modified
2. **Ordering**: Events must be totally ordered within a stream
3. **Concurrency**: Use optimistic concurrency control
4. **Snapshots**: Implement for performance on large streams
5. **Retention**: Configure retention policies for old events
