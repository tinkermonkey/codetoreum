# IEventStore Output Port Design

## Overview

The `IEventStore` port provides an abstraction for event sourcing and event persistence. All domain events are stored through this port, enabling event replay, audit trails, and debugging capabilities.

**Persistence Architecture**: Two-tier design for performance and durability:
```
Application → IEventStore → Redis Buffer → Background Workers → Elasticsearch (persistence)
```

**Production Implementation**: `ElasticsearchEventStore` with `RedisEventBuffer`
**Testing Implementation**: `InMemoryEventStore`

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

### Current Event Store Implementation (v1.0)

The current implementation uses **in-memory event store** for simplicity and simulation support:

```python
class InMemoryEventStore(IEventStore):
    """
    In-memory event store for development and testing.

    Events are stored in memory and lost on restart.
    Suitable for simulation mode and testing workflows.
    """
```

### Planned: Elasticsearch Event Store with Redis Buffering

The planned production implementation uses **Elasticsearch for persistence** with **Redis for buffering**:

```python
class ElasticsearchEventStore(IEventStore):
    """
    Production event store using Elasticsearch with Redis buffering.

    Architecture:
    1. Events written to Redis Stream for immediate acknowledgment
    2. Background workers consume from Redis and batch-persist to Elasticsearch
    3. Queries read from Elasticsearch for durability

    This provides:
    - High write throughput (Redis buffering)
    - Data durability (Elasticsearch persistence)
    - Event replay capability (Elasticsearch queries)
    """

    def __init__(
        self,
        es_client,
        redis_client,
        index_prefix: str = "events"
    ):
        self.es = es_client
        self.redis = redis_client
        self.index_prefix = index_prefix

    async def append(self,
                     stream_id: str,
                     events: List[DomainEvent],
                     expected_version: Optional[int] = None) -> None:
        """
        Append events via Redis buffer.

        Events are:
        1. Validated for optimistic concurrency
        2. Written to Redis Stream (fast acknowledgment)
        3. Asynchronously persisted to Elasticsearch by background workers
        """
        # Check version if specified (query Elasticsearch)
        if expected_version is not None:
            current = await self._get_stream_version_from_es(stream_id)
            if current != expected_version:
                raise ConcurrencyConflictError(
                    f"Expected version {expected_version}, got {current}"
                )

        # Buffer events in Redis for asynchronous persistence
        for event in events:
            await self.redis.xadd(
                "events:buffer",
                {
                    'stream_id': stream_id,
                    'event_id': str(event.event_id),
                    'event_type': event.event_type,
                    'aggregate_type': event.aggregate_type,
                    'version': event.version,
                    'timestamp': event.timestamp.isoformat(),
                    'data': json.dumps(event.data),
                    'metadata': json.dumps(event.metadata)
                }
            )

    async def get_events(self,
                        stream_id: str,
                        from_version: int = 0,
                        to_version: Optional[int] = None) -> List[DomainEvent]:
        """Retrieve events from Elasticsearch."""
        query = {
            "bool": {
                "must": [
                    {"term": {"stream_id": stream_id}},
                    {"range": {"version": {"gte": from_version}}}
                ]
            }
        }

        if to_version is not None:
            query["bool"]["must"].append({
                "range": {"version": {"lte": to_version}}
            })

        response = await self.es.search(
            index=f"{self.index_prefix}-*",
            query=query,
            sort=[{"version": "asc"}],
            size=10000
        )

        return [
            self._doc_to_domain_event(hit["_source"])
            for hit in response["hits"]["hits"]
        ]

    async def _get_stream_version_from_es(self, stream_id: str) -> int:
        """Get current stream version from Elasticsearch."""
        # Query for latest event in stream
        response = await self.es.search(
            index=f"{self.index_prefix}-*",
            query={"term": {"stream_id": stream_id}},
            sort=[{"version": "desc"}],
            size=1
        )

        if response["hits"]["hits"]:
            return response["hits"]["hits"][0]["_source"]["version"]
        return 0
```

**Background Worker** (separate process):
```python
class EventPersistenceWorker:
    """
    Consumes events from Redis and persists to Elasticsearch.

    Deployed as separate worker processes for:
    - Decoupling write acknowledgment from persistence
    - Batch processing for efficiency
    - Parallel processing with consumer groups
    """

    async def run(self):
        """Main worker loop."""
        while True:
            # Read batch from Redis Stream
            messages = await self.redis.xreadgroup(
                groupname="elasticsearch-writers",
                consumername=self.worker_id,
                streams={"events:buffer": ">"},
                count=100,
                block=1000
            )

            if not messages:
                continue

            # Batch write to Elasticsearch
            events = [self._parse_event(msg) for _, msgs in messages for msg in msgs]
            await self._bulk_insert_to_elasticsearch(events)

            # Acknowledge processing
            message_ids = [msg[0] for _, msgs in messages for msg in msgs]
            await self.redis.xack("events:buffer", "elasticsearch-writers", *message_ids)
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

## Consistency and Durability Guarantees

### Production (Elasticsearch + Redis)

**Write Acknowledgment**:
- Events are **immediately acknowledged** after Redis write
- Application can continue without waiting for Elasticsearch persistence

**Durability**:
- **Eventual Consistency**: Events visible in Elasticsearch within seconds (typically < 5s)
- **Redis Persistence**: RDB + AOF prevents data loss on Redis restart
- **Consumer Groups**: Guarantee no message loss during worker processing
- **Retries**: Failed Elasticsearch writes automatically retried

**Query Consistency**:
- Event queries read from Elasticsearch (durable storage)
- Recently written events may have slight lag before queryable
- For strict consistency needs, can query Redis buffer + Elasticsearch

**Failure Scenarios**:
| Scenario | Outcome | Recovery |
|----------|---------|----------|
| Redis crash | No data loss (RDB + AOF) | Workers resume from last ACK |
| Elasticsearch crash | Events buffered in Redis | Workers retry when ES recovers |
| Worker crash | Unacknowledged messages reprocessed | Consumer group handles retry |
| Network partition | Events buffered until recovery | Automatic catch-up |

### Testing (In-Memory)

**Consistency**:
- **Immediate Consistency**: All writes immediately visible
- **No Buffering**: Synchronous append to in-memory store
- **Perfect for Testing**: Deterministic, fast, no eventual consistency complexity

## Integration Points

### Used By
- Domain Models (for emitting events)
- Application Services (for event-driven workflows)
- Event Processors (for consuming events)
- Background Workers (for event persistence)

### Dependencies
- **Production**: Elasticsearch client, Redis client
- **Testing**: None (in-memory)

## Implementation Notes

1. **Immutability**: Events are append-only, never modified
2. **Ordering**: Events must be totally ordered within a stream
3. **Concurrency**: Use optimistic concurrency control (version checking)
4. **Snapshots**: Optional for performance on large streams
5. **Retention**: Configure ILM policies in Elasticsearch
6. **Buffering**: Monitor Redis buffer depth to prevent backlog
7. **Worker Scaling**: Add workers if buffer lag increases
