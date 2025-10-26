# Redis External System - Detailed Design

## Overview

Redis serves as the **high-performance buffering and caching layer** for the Codetoreum platform. It provides the critical bridge between the application and Elasticsearch, enabling high write throughput while maintaining data durability.

**Architecture Role**: Redis is NOT the primary persistence layer. It serves as:
- **Write Buffer**: Events, logs, and metrics are written to Redis first, then asynchronously persisted to Elasticsearch
- **Read Cache**: Frequently accessed configurations and projections are cached for fast access
- **Real-Time Layer**: Pub/sub for real-time event broadcasting and task queuing

**Data Flow**:
```
Application → Redis (buffer/cache) → Background Workers → Elasticsearch (persistent storage)
```

## System Purpose

**Primary Functions**:

### 1. **Buffering Layer** (Critical)
- **Event Buffering**: Events written to Redis Streams, then batch-persisted to Elasticsearch
- **Log Buffering**: Logs buffered before bulk insertion to Elasticsearch
- **Metrics Buffering**: Real-time metrics aggregated and batched
- **Backpressure Handling**: Prevents Elasticsearch overload during traffic spikes

### 2. **Caching Layer** (Performance)
- **Configuration Cache**: Hot configurations cached for sub-millisecond access
- **Projection Cache**: Read model projections cached to reduce Elasticsearch queries
- **Session State**: Temporary session and execution state
- **Health Status Cache**: System health and container status

### 3. **Task Queue** (Coordination)
- **Agent Execution Queue**: Priority-based task scheduling
- **Background Job Queue**: Asynchronous task processing
- **Worker Coordination**: Distributed lock and worker assignment

### 4. **Real-Time Communication** (Pub/Sub)
- **Event Broadcasting**: Real-time event notifications to subscribers
- **Log Streaming**: Live log tail for active executions
- **Progress Updates**: Real-time workflow progress to UI clients

## Port Interface Design

### IQueue Interface

```python
from abc import ABC, abstractmethod
from typing import List, Dict, Optional, Any
from dataclasses import dataclass
from enum import Enum
from datetime import datetime

class TaskPriority(Enum):
    """Task priority levels."""
    LOW = 1
    MEDIUM = 2
    HIGH = 3
    CRITICAL = 4

@dataclass
class Task:
    """A task in the queue."""
    id: str
    agent: str
    project: str
    priority: TaskPriority
    context: Dict[str, Any]
    created_at: datetime

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to dictionary."""
        return {
            'id': self.id,
            'agent': self.agent,
            'project': self.project,
            'priority': self.priority.value,
            'context': self.context,
            'created_at': self.created_at.isoformat()
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'Task':
        """Deserialize from dictionary."""
        return cls(
            id=data['id'],
            agent=data['agent'],
            project=data['project'],
            priority=TaskPriority(data['priority']),
            context=data['context'],
            created_at=datetime.fromisoformat(data['created_at'])
        )

class IQueue(ABC):
    """
    Port interface for task queue operations.

    Abstracts Redis, in-memory, and database queues.
    """

    @abstractmethod
    async def enqueue(self, task: Task) -> None:
        """
        Add task to queue.

        Tasks are ordered by priority (high to low), then by timestamp (old to new).
        """
        pass

    @abstractmethod
    async def dequeue(self) -> Optional[Task]:
        """
        Remove and return highest priority task.

        Returns None if queue is empty.
        """
        pass

    @abstractmethod
    async def peek(self) -> Optional[Task]:
        """
        View highest priority task without removing.

        Returns None if queue is empty.
        """
        pass

    @abstractmethod
    async def size(self) -> int:
        """Get number of tasks in queue."""
        pass

    @abstractmethod
    async def clear(self) -> int:
        """
        Remove all tasks from queue.

        Returns number of tasks removed.
        """
        pass

    @abstractmethod
    async def list_tasks(
        self,
        limit: Optional[int] = None
    ) -> List[Task]:
        """
        List tasks in queue (without removing).

        Args:
            limit: Maximum number of tasks to return

        Returns:
            List of tasks in priority order
        """
        pass
```

### IEventStream Interface

```python
from typing import AsyncGenerator

@dataclass
class StreamEvent:
    """An event in the stream."""
    id: str
    data: Dict[str, Any]
    timestamp: datetime

class IEventStream(ABC):
    """
    Port interface for event streaming.

    Abstracts Redis pub/sub and streams.
    """

    @abstractmethod
    async def publish(
        self,
        channel: str,
        event: Dict[str, Any]
    ) -> None:
        """
        Publish event to channel.

        For real-time delivery to subscribers.
        """
        pass

    @abstractmethod
    async def subscribe(
        self,
        channel: str,
        callback: Callable[[Dict[str, Any]], None]
    ) -> None:
        """
        Subscribe to channel.

        Callback invoked for each received event.
        """
        pass

    @abstractmethod
    async def add_to_stream(
        self,
        stream_name: str,
        event: Dict[str, Any]
    ) -> str:
        """
        Add event to stream.

        For persistent event history.

        Returns:
            Event ID
        """
        pass

    @abstractmethod
    async def read_stream(
        self,
        stream_name: str,
        start_id: str = "0",
        count: Optional[int] = None
    ) -> List[StreamEvent]:
        """
        Read events from stream.

        Args:
            stream_name: Stream to read from
            start_id: ID to start reading from
            count: Maximum events to return

        Returns:
            List of events
        """
        pass
```

### ICache Interface

```python
class ICache(ABC):
    """
    Port interface for caching operations.

    Abstracts Redis, in-memory, and other caches.
    """

    @abstractmethod
    async def get(self, key: str) -> Optional[str]:
        """Get value by key."""
        pass

    @abstractmethod
    async def set(
        self,
        key: str,
        value: str,
        ttl: Optional[int] = None
    ) -> None:
        """
        Set key-value pair.

        Args:
            key: Cache key
            value: Value to store
            ttl: Time to live in seconds (None = no expiration)
        """
        pass

    @abstractmethod
    async def delete(self, key: str) -> bool:
        """
        Delete key.

        Returns:
            True if key existed and was deleted
        """
        pass

    @abstractmethod
    async def exists(self, key: str) -> bool:
        """Check if key exists."""
        pass

    @abstractmethod
    async def keys(self, pattern: str) -> List[str]:
        """
        Find keys matching pattern.

        Pattern uses glob-style wildcards (* and ?).
        """
        pass

    @abstractmethod
    async def expire(self, key: str, ttl: int) -> bool:
        """
        Set expiration on existing key.

        Returns:
            True if expiration was set
        """
        pass
```

## Production Adapter: RedisAdapter

### Implementation Structure

```python
import redis.asyncio as aioredis
import json
from typing import Optional

class RedisQueueAdapter(IQueue):
    """
    Production adapter for Redis-based task queue.

    Uses Redis sorted set for priority queue.
    """

    def __init__(
        self,
        redis_host: str = "localhost",
        redis_port: int = 6379,
        redis_db: int = 0,
        queue_key: str = "orchestrator:tasks:queue"
    ):
        """
        Initialize Redis queue adapter.

        Args:
            redis_host: Redis server hostname
            redis_port: Redis server port
            redis_db: Redis database number
            queue_key: Redis key for queue storage
        """
        self.redis = aioredis.Redis(
            host=redis_host,
            port=redis_port,
            db=redis_db,
            decode_responses=True
        )
        self.queue_key = queue_key

    async def enqueue(self, task: Task) -> None:
        """
        Add task to Redis sorted set.

        Score calculation ensures:
        1. Higher priority = lower score (comes first)
        2. Older timestamp = lower score (FIFO within priority)
        """
        # Calculate score: -(priority * 1000 + timestamp)
        # Negative so higher priority = lower score
        timestamp = task.created_at.timestamp()
        score = -(task.priority.value * 1000 + timestamp)

        # Serialize task
        task_json = json.dumps(task.to_dict())

        # Add to sorted set
        await self.redis.zadd(
            self.queue_key,
            {task_json: score}
        )

    async def dequeue(self) -> Optional[Task]:
        """
        Remove and return lowest score (highest priority, oldest).

        Uses ZPOPMIN for atomic pop operation.
        """
        result = await self.redis.zpopmin(self.queue_key, count=1)

        if not result:
            return None

        task_json, score = result[0]
        task_data = json.loads(task_json)
        return Task.from_dict(task_data)

    async def peek(self) -> Optional[Task]:
        """
        View lowest score without removing.

        Uses ZRANGE with limit.
        """
        results = await self.redis.zrange(
            self.queue_key,
            0, 0,
            withscores=False
        )

        if not results:
            return None

        task_json = results[0]
        task_data = json.loads(task_json)
        return Task.from_dict(task_data)

    async def size(self) -> int:
        """Get queue size using ZCARD."""
        return await self.redis.zcard(self.queue_key)

    async def clear(self) -> int:
        """Clear queue and return count removed."""
        count = await self.size()
        await self.redis.delete(self.queue_key)
        return count

    async def list_tasks(
        self,
        limit: Optional[int] = None
    ) -> List[Task]:
        """List tasks in priority order."""
        end = limit - 1 if limit else -1

        results = await self.redis.zrange(
            self.queue_key,
            0, end,
            withscores=False
        )

        tasks = []
        for task_json in results:
            task_data = json.loads(task_json)
            tasks.append(Task.from_dict(task_data))

        return tasks


class RedisEventStreamAdapter(IEventStream):
    """
    Production adapter for Redis event streaming.

    Uses Redis pub/sub for real-time and streams for history.
    """

    def __init__(
        self,
        redis_host: str = "localhost",
        redis_port: int = 6379,
        redis_db: int = 0
    ):
        self.redis = aioredis.Redis(
            host=redis_host,
            port=redis_port,
            db=redis_db,
            decode_responses=True
        )
        self.pubsub = self.redis.pubsub()

    async def publish(
        self,
        channel: str,
        event: Dict[str, Any]
    ) -> None:
        """Publish to Redis pub/sub channel."""
        event_json = json.dumps(event)
        await self.redis.publish(channel, event_json)

    async def subscribe(
        self,
        channel: str,
        callback: Callable[[Dict[str, Any]], None]
    ) -> None:
        """
        Subscribe to channel with callback.

        Runs in background, calling callback for each message.
        """
        await self.pubsub.subscribe(channel)

        async for message in self.pubsub.listen():
            if message['type'] == 'message':
                data = json.loads(message['data'])
                callback(data)

    async def add_to_stream(
        self,
        stream_name: str,
        event: Dict[str, Any]
    ) -> str:
        """
        Add event to Redis stream.

        Uses XADD with maxlen for automatic trimming.
        """
        event_id = await self.redis.xadd(
            stream_name,
            event,
            maxlen=1000,  # Keep last 1000 events
            approximate=True
        )

        return event_id

    async def read_stream(
        self,
        stream_name: str,
        start_id: str = "0",
        count: Optional[int] = None
    ) -> List[StreamEvent]:
        """Read from Redis stream."""
        results = await self.redis.xrange(
            stream_name,
            min=start_id,
            max="+",
            count=count
        )

        events = []
        for event_id, data in results:
            events.append(StreamEvent(
                id=event_id,
                data=data,
                timestamp=self._parse_stream_id_timestamp(event_id)
            ))

        return events

    def _parse_stream_id_timestamp(self, event_id: str) -> datetime:
        """Extract timestamp from Redis stream ID."""
        # Stream ID format: milliseconds-sequence
        millis = int(event_id.split('-')[0])
        return datetime.fromtimestamp(millis / 1000)


class RedisCacheAdapter(ICache):
    """Production adapter for Redis caching."""

    def __init__(
        self,
        redis_host: str = "localhost",
        redis_port: int = 6379,
        redis_db: int = 0
    ):
        self.redis = aioredis.Redis(
            host=redis_host,
            port=redis_port,
            db=redis_db,
            decode_responses=True
        )

    async def get(self, key: str) -> Optional[str]:
        """Get value from Redis."""
        return await self.redis.get(key)

    async def set(
        self,
        key: str,
        value: str,
        ttl: Optional[int] = None
    ) -> None:
        """Set value in Redis with optional TTL."""
        if ttl:
            await self.redis.setex(key, ttl, value)
        else:
            await self.redis.set(key, value)

    async def delete(self, key: str) -> bool:
        """Delete key from Redis."""
        count = await self.redis.delete(key)
        return count > 0

    async def exists(self, key: str) -> bool:
        """Check if key exists."""
        count = await self.redis.exists(key)
        return count > 0

    async def keys(self, pattern: str) -> List[str]:
        """Find keys matching pattern."""
        return await self.redis.keys(pattern)

    async def expire(self, key: str, ttl: int) -> bool:
        """Set expiration on key."""
        return await self.redis.expire(key, ttl)
```

## Mock Adapters

### InMemoryQueueAdapter

```python
import heapq
from typing import List

class InMemoryQueueAdapter(IQueue):
    """
    Mock queue adapter using in-memory heap.

    Fully functional without Redis dependency.
    """

    def __init__(self):
        self.heap: List[tuple] = []  # (score, task_json)
        self.counter = 0  # For stable sorting

    async def enqueue(self, task: Task) -> None:
        """Add task to heap."""
        # Calculate score (same logic as Redis)
        timestamp = task.created_at.timestamp()
        score = -(task.priority.value * 1000 + timestamp)

        # Use counter for stable sort
        heapq.heappush(
            self.heap,
            (score, self.counter, task)
        )
        self.counter += 1

    async def dequeue(self) -> Optional[Task]:
        """Pop lowest score (highest priority)."""
        if not self.heap:
            return None

        score, counter, task = heapq.heappop(self.heap)
        return task

    async def peek(self) -> Optional[Task]:
        """View without removing."""
        if not self.heap:
            return None

        score, counter, task = self.heap[0]
        return task

    async def size(self) -> int:
        """Get queue size."""
        return len(self.heap)

    async def clear(self) -> int:
        """Clear queue."""
        count = len(self.heap)
        self.heap = []
        return count

    async def list_tasks(
        self,
        limit: Optional[int] = None
    ) -> List[Task]:
        """List tasks in priority order."""
        sorted_tasks = sorted(self.heap, key=lambda x: x[0])

        tasks = [task for score, counter, task in sorted_tasks]

        if limit:
            return tasks[:limit]

        return tasks


class InMemoryEventStreamAdapter(IEventStream):
    """Mock event stream using in-memory storage."""

    def __init__(self):
        self.streams: Dict[str, List[StreamEvent]] = {}
        self.subscribers: Dict[str, List[Callable]] = {}
        self.event_counter = 0

    async def publish(
        self,
        channel: str,
        event: Dict[str, Any]
    ) -> None:
        """Publish to in-memory subscribers."""
        if channel in self.subscribers:
            for callback in self.subscribers[channel]:
                callback(event)

    async def subscribe(
        self,
        channel: str,
        callback: Callable[[Dict[str, Any]], None]
    ) -> None:
        """Register callback for channel."""
        if channel not in self.subscribers:
            self.subscribers[channel] = []

        self.subscribers[channel].append(callback)

    async def add_to_stream(
        self,
        stream_name: str,
        event: Dict[str, Any]
    ) -> str:
        """Add event to in-memory stream."""
        if stream_name not in self.streams:
            self.streams[stream_name] = []

        event_id = f"{int(datetime.utcnow().timestamp() * 1000)}-{self.event_counter}"
        self.event_counter += 1

        stream_event = StreamEvent(
            id=event_id,
            data=event,
            timestamp=datetime.utcnow()
        )

        self.streams[stream_name].append(stream_event)

        # Trim to max 1000
        if len(self.streams[stream_name]) > 1000:
            self.streams[stream_name] = self.streams[stream_name][-1000:]

        return event_id

    async def read_stream(
        self,
        stream_name: str,
        start_id: str = "0",
        count: Optional[int] = None
    ) -> List[StreamEvent]:
        """Read from in-memory stream."""
        if stream_name not in self.streams:
            return []

        events = self.streams[stream_name]

        # Filter by start_id
        if start_id != "0":
            events = [e for e in events if e.id > start_id]

        # Apply limit
        if count:
            events = events[:count]

        return events


class InMemoryCacheAdapter(ICache):
    """Mock cache using in-memory dictionary."""

    def __init__(self):
        self.data: Dict[str, tuple] = {}  # {key: (value, expire_at)}

    async def get(self, key: str) -> Optional[str]:
        """Get value if not expired."""
        if key not in self.data:
            return None

        value, expire_at = self.data[key]

        if expire_at and datetime.utcnow() > expire_at:
            # Expired
            del self.data[key]
            return None

        return value

    async def set(
        self,
        key: str,
        value: str,
        ttl: Optional[int] = None
    ) -> None:
        """Set value with optional expiration."""
        expire_at = None
        if ttl:
            expire_at = datetime.utcnow() + timedelta(seconds=ttl)

        self.data[key] = (value, expire_at)

    async def delete(self, key: str) -> bool:
        """Delete key."""
        if key in self.data:
            del self.data[key]
            return True
        return False

    async def exists(self, key: str) -> bool:
        """Check existence (checking expiration)."""
        value = await self.get(key)
        return value is not None

    async def keys(self, pattern: str) -> List[str]:
        """Find keys matching glob pattern."""
        import fnmatch

        # Clean up expired keys first
        for key in list(self.data.keys()):
            await self.get(key)  # Triggers expiration check

        return [
            key for key in self.data.keys()
            if fnmatch.fnmatch(key, pattern)
        ]

    async def expire(self, key: str, ttl: int) -> bool:
        """Set expiration on existing key."""
        if key not in self.data:
            return False

        value, _ = self.data[key]
        expire_at = datetime.utcnow() + timedelta(seconds=ttl)
        self.data[key] = (value, expire_at)
        return True
```

## Error Handling

```python
class RedisError(Exception):
    """Base exception for Redis operations."""
    pass

class ConnectionError(RedisError):
    """Raised when connection to Redis fails."""
    pass

class QueueError(RedisError):
    """Raised when queue operation fails."""
    pass
```

## Configuration

```python
@dataclass
class RedisConfig:
    """Redis adapter configuration."""
    host: str = "localhost"
    port: int = 6379
    db: int = 0
    password: Optional[str] = None

    # Queue settings
    queue_key: str = "orchestrator:tasks:queue"

    # Stream settings
    event_stream_key: str = "orchestrator:event_stream"
    event_stream_maxlen: int = 1000
    event_channel: str = "orchestrator:agent_events"

    # Connection settings
    connection_timeout: int = 5
    socket_keepalive: bool = True
    max_connections: int = 50

    # Retry settings
    retry_on_timeout: bool = True
    max_retries: int = 3
```

## Testing Strategy

### Unit Tests

```python
import pytest

@pytest.fixture
def memory_queue():
    return InMemoryQueueAdapter()

async def test_queue_priority(memory_queue):
    """Test priority ordering."""
    low_task = Task(
        id="1",
        agent="test",
        project="test",
        priority=TaskPriority.LOW,
        context={},
        created_at=datetime.utcnow()
    )

    high_task = Task(
        id="2",
        agent="test",
        project="test",
        priority=TaskPriority.HIGH,
        context={},
        created_at=datetime.utcnow()
    )

    # Enqueue in wrong order
    await memory_queue.enqueue(low_task)
    await memory_queue.enqueue(high_task)

    # Dequeue should return high priority first
    first = await memory_queue.dequeue()
    assert first.id == "2"

    second = await memory_queue.dequeue()
    assert second.id == "1"

async def test_cache_expiration(InMemoryCacheAdapter):
    """Test TTL expiration."""
    cache = InMemoryCacheAdapter()

    await cache.set("key1", "value1", ttl=1)
    assert await cache.get("key1") == "value1"

    # Wait for expiration
    await asyncio.sleep(2)

    assert await cache.get("key1") is None
```

## Deployment Considerations

### Data Persistence

Redis persistence options:
- **RDB (snapshots)**: Periodic snapshots, good for backups
- **AOF (append-only file)**: Logs every write, more durable
- **Both**: Maximum durability

**Recommendation**: Use AOF for queue and cache to prevent task loss.

### Memory Management

```python
class RedisMemoryMonitor:
    """Monitor Redis memory usage."""

    def __init__(self, redis_client):
        self.redis = redis_client

    async def get_memory_stats(self) -> Dict[str, Any]:
        """Get memory usage statistics."""
        info = await self.redis.info('memory')

        return {
            'used_memory': info['used_memory'],
            'used_memory_human': info['used_memory_human'],
            'maxmemory': info.get('maxmemory', 0),
            'maxmemory_policy': info.get('maxmemory_policy', 'noeviction')
        }

    async def is_memory_critical(self) -> bool:
        """Check if memory usage is critical."""
        stats = await self.get_memory_stats()

        if stats['maxmemory'] == 0:
            return False

        usage_percent = (stats['used_memory'] / stats['maxmemory']) * 100
        return usage_percent > 90
```

## Buffering Architecture for Elasticsearch

### Event Buffering

**Purpose**: Buffer domain events before persisting to Elasticsearch

**Implementation**:
```python
class RedisEventBuffer:
    """
    Buffers domain events in Redis Streams before Elasticsearch persistence.

    Architecture:
    - Events written to Redis Stream for immediate acknowledgment
    - Consumer groups ensure reliable delivery
    - Background workers batch-write to Elasticsearch
    - Provides high write throughput with eventual consistency
    """

    def __init__(self, redis_client):
        self.redis = redis_client
        self.stream_name = "events:buffer"
        self.consumer_group = "elasticsearch-writers"

    async def buffer_event(self, event: Dict[str, Any]) -> str:
        """
        Write event to Redis Stream.

        Returns:
            Message ID from Redis
        """
        message_id = await self.redis.xadd(
            self.stream_name,
            {
                "event_id": event["event_id"],
                "aggregate_id": event["aggregate_id"],
                "event_type": event["event_type"],
                "payload": json.dumps(event)
            }
        )
        return message_id

    async def buffer_events_bulk(self, events: List[Dict[str, Any]]) -> List[str]:
        """Batch buffer multiple events."""
        message_ids = []
        for event in events:
            message_id = await self.buffer_event(event)
            message_ids.append(message_id)
        return message_ids

class EventPersistenceWorker:
    """
    Background worker that consumes events from Redis and persists to Elasticsearch.

    Uses consumer groups for:
    - Reliable delivery (no message loss)
    - Parallel processing (multiple workers)
    - Automatic retry on failure
    """

    def __init__(
        self,
        redis_client,
        elasticsearch_store,
        worker_id: str,
        batch_size: int = 100
    ):
        self.redis = redis_client
        self.es_store = elasticsearch_store
        self.worker_id = worker_id
        self.batch_size = batch_size
        self.stream_name = "events:buffer"
        self.consumer_group = "elasticsearch-writers"

    async def process_events_loop(self):
        """Main processing loop."""
        while True:
            try:
                # Read batch from Redis Stream
                messages = await self.redis.xreadgroup(
                    groupname=self.consumer_group,
                    consumername=self.worker_id,
                    streams={self.stream_name: ">"},
                    count=self.batch_size,
                    block=1000  # Block for 1 second if no messages
                )

                if not messages:
                    continue

                # Parse and batch write to Elasticsearch
                events = [self._parse_event(msg) for _, msg_list in messages for msg in msg_list]
                await self.es_store.bulk_insert_events(events)

                # Acknowledge successful processing
                message_ids = [msg[0] for _, msg_list in messages for msg in msg_list]
                await self.redis.xack(
                    self.stream_name,
                    self.consumer_group,
                    *message_ids
                )

            except Exception as e:
                # Log error, message will be retried
                logger.error(f"Event persistence worker error: {e}")
                await asyncio.sleep(5)  # Back off on error

    def _parse_event(self, message: tuple) -> Dict[str, Any]:
        """Parse event from Redis message."""
        msg_id, fields = message
        return json.loads(fields[b"payload"])
```

**Monitoring Metrics**:
```python
async def get_buffer_metrics(redis_client) -> Dict[str, int]:
    """Get event buffer health metrics."""
    stream_info = await redis_client.xinfo_stream("events:buffer")
    pending_info = await redis_client.xpending("events:buffer", "elasticsearch-writers")

    return {
        "total_events": stream_info["length"],
        "pending_events": pending_info["pending"],
        "consumer_count": len(stream_info["groups"]),
        "lag_ms": calculate_lag_milliseconds(stream_info)
    }
```

### Log Buffering

**Purpose**: Buffer application and execution logs before Elasticsearch persistence

**Implementation**:
```python
class RedisLogBuffer:
    """
    Buffers log entries before Elasticsearch persistence.

    Optimizations:
    - Batch writes for high throughput
    - Separate stream for each log level for priority processing
    - TTL to prevent memory exhaustion
    """

    def __init__(self, redis_client):
        self.redis = redis_client

    async def buffer_log(self, log_entry: Dict[str, Any]) -> None:
        """Write log to appropriate stream based on level."""
        level = log_entry.get("level", "INFO")
        stream_name = f"logs:buffer:{level.lower()}"

        await self.redis.xadd(
            stream_name,
            {
                "timestamp": log_entry["timestamp"],
                "message": log_entry["message"],
                "payload": json.dumps(log_entry)
            },
            maxlen=100000,  # Prevent unbounded growth
            approximate=True
        )

class LogPersistenceWorker:
    """Persists logs from Redis to Elasticsearch in batches."""

    async def process_logs_loop(self):
        """Process logs with priority: ERROR > WARN > INFO > DEBUG."""
        levels = ["error", "warn", "info", "debug"]

        while True:
            for level in levels:
                stream_name = f"logs:buffer:{level}"
                messages = await self.redis.xreadgroup(
                    groupname="log-writers",
                    consumername=self.worker_id,
                    streams={stream_name: ">"},
                    count=500
                )

                if messages:
                    logs = [self._parse_log(msg) for _, msg_list in messages for msg in msg_list]
                    await self.es_store.bulk_insert_logs(logs)
                    # Acknowledge...

            await asyncio.sleep(0.1)  # 100ms cycle
```

### Configuration Caching

**Purpose**: Cache hot configurations for sub-millisecond access

**Implementation**:
```python
class RedisConfigCache:
    """
    Write-through cache for configuration data.

    Architecture:
    - All writes go to both Elasticsearch (source of truth) and Redis (cache)
    - Reads check Redis first, fall back to Elasticsearch
    - Cache invalidation via pub/sub
    - TTL as safety net
    """

    def __init__(self, redis_client, es_config_store):
        self.redis = redis_client
        self.es_store = es_config_store
        self.ttl = 3600  # 1 hour

    async def get_project_config(self, project_id: str) -> Optional[Dict[str, Any]]:
        """Get project config from cache or Elasticsearch."""
        # Check cache first
        cache_key = f"config:project:{project_id}"
        cached = await self.redis.get(cache_key)

        if cached:
            return json.loads(cached)

        # Cache miss - fetch from Elasticsearch
        config = await self.es_store.get_project(project_id)

        if config:
            # Populate cache
            await self.redis.setex(
                cache_key,
                self.ttl,
                json.dumps(config.to_dict())
            )

        return config

    async def save_project_config(self, config: ProjectConfig) -> str:
        """Save config to Elasticsearch and update cache."""
        # Write to Elasticsearch (source of truth)
        config_id = await self.es_store.save_project(config)

        # Update cache (write-through)
        cache_key = f"config:project:{config.project_id}"
        await self.redis.setex(
            cache_key,
            self.ttl,
            json.dumps(config.to_dict())
        )

        # Broadcast invalidation to other nodes
        await self.redis.publish(
            "config:invalidate",
            json.dumps({"type": "project", "id": config.project_id})
        )

        return config_id

    async def invalidate_config(self, config_type: str, config_id: str) -> None:
        """Invalidate cached configuration."""
        cache_key = f"config:{config_type}:{config_id}"
        await self.redis.delete(cache_key)
```

**Cache Invalidation Subscriber**:
```python
class ConfigCacheInvalidationSubscriber:
    """Listens for cache invalidation events."""

    async def subscribe(self):
        """Subscribe to invalidation channel."""
        pubsub = self.redis.pubsub()
        await pubsub.subscribe("config:invalidate")

        async for message in pubsub.listen():
            if message["type"] == "message":
                data = json.loads(message["data"])
                config_type = data["type"]
                config_id = data["id"]

                # Invalidate local cache
                cache_key = f"config:{config_type}:{config_id}"
                await self.redis.delete(cache_key)
```

### Metrics Buffering and Aggregation

**Purpose**: Buffer and pre-aggregate metrics before Elasticsearch persistence

**Implementation**:
```python
class RedisMetricsBuffer:
    """
    Buffers and aggregates metrics before Elasticsearch persistence.

    Features:
    - Real-time counters and gauges
    - Pre-aggregation to reduce Elasticsearch writes
    - Periodic flush to Elasticsearch
    """

    async def record_metric(
        self,
        metric_name: str,
        value: float,
        tags: Dict[str, str]
    ) -> None:
        """Record a metric value."""
        timestamp = int(time.time())
        metric_key = self._make_metric_key(metric_name, tags, timestamp)

        # Increment counter or update gauge
        await self.redis.hincrby(f"metrics:raw:{metric_key}", "count", 1)
        await self.redis.hincrbyfloat(f"metrics:raw:{metric_key}", "sum", value)

        # Set expiry to prevent memory leak
        await self.redis.expire(f"metrics:raw:{metric_key}", 3600)

class MetricsAggregationWorker:
    """Aggregates and persists metrics to Elasticsearch."""

    async def aggregate_and_persist_loop(self):
        """Aggregate metrics and persist every minute."""
        while True:
            # Scan for metric keys
            pattern = "metrics:raw:*"
            cursor = 0

            aggregated_metrics = []

            while True:
                cursor, keys = await self.redis.scan(
                    cursor,
                    match=pattern,
                    count=100
                )

                for key in keys:
                    # Get aggregated data
                    data = await self.redis.hgetall(key)
                    count = int(data.get(b"count", 0))
                    sum_val = float(data.get(b"sum", 0.0))

                    metric = {
                        "metric_name": self._parse_metric_name(key),
                        "avg_value": sum_val / count if count > 0 else 0,
                        "count": count,
                        "sum": sum_val
                    }
                    aggregated_metrics.append(metric)

                    # Delete processed key
                    await self.redis.delete(key)

                if cursor == 0:
                    break

            # Bulk write to Elasticsearch
            if aggregated_metrics:
                await self.es_store.bulk_insert_metrics(aggregated_metrics)

            await asyncio.sleep(60)  # Aggregate every minute
```

## Data Durability and Recovery

### Redis Persistence Configuration

```python
# Recommended Redis configuration for production
CONFIG = {
    # Enable both RDB and AOF for maximum durability
    "save": "900 1 300 10 60 10000",  # RDB snapshots
    "appendonly": "yes",                # AOF enabled
    "appendfsync": "everysec",          # AOF sync every second
    "auto-aof-rewrite-percentage": 100,
    "auto-aof-rewrite-min-size": "64mb",

    # Memory management
    "maxmemory": "4gb",
    "maxmemory-policy": "allkeys-lru",  # Evict oldest keys when full

    # Stream configuration
    "stream-node-max-entries": 100000,
}
```

### Disaster Recovery

**Scenario**: Redis failure with buffered events not yet persisted to Elasticsearch

**Recovery Strategy**:
1. Redis persistence (RDB + AOF) prevents data loss on restart
2. Consumer groups track last processed message ID
3. On recovery, workers resume from last acknowledged position
4. No event loss as long as Redis data persists

**Code**:
```python
async def recover_buffer_on_startup():
    """Ensure consumer group exists and resume processing."""
    try:
        # Create consumer group if it doesn't exist
        await redis.xgroup_create(
            "events:buffer",
            "elasticsearch-writers",
            id="0",
            mkstream=True
        )
    except:
        # Group already exists
        pass

    # Check for pending messages (not acknowledged)
    pending = await redis.xpending(
        "events:buffer",
        "elasticsearch-writers"
    )

    if pending["pending"] > 0:
        logger.warning(f"Found {pending['pending']} pending events, will retry")

    # Start workers - they will automatically process pending messages
```

## Summary

The Redis integration provides:

1. **High-Performance Buffering**:
   - Events buffered for batch Elasticsearch writes
   - Logs buffered with priority processing
   - Metrics pre-aggregated before persistence

2. **Intelligent Caching**:
   - Configuration caching with write-through strategy
   - Projection caching for fast queries
   - Cache invalidation via pub/sub

3. **Reliability**:
   - Consumer groups for guaranteed delivery
   - RDB + AOF persistence prevents data loss
   - Automatic recovery after failures

4. **Scalability**:
   - Multiple workers for parallel processing
   - Backpressure handling protects Elasticsearch
   - Horizontal scaling via additional workers

5. **Observability**:
   - Buffer depth monitoring
   - Lag metrics and alerts
   - Processing throughput tracking

**Key Principle**: Redis is the **transient buffer and cache**, Elasticsearch is the **source of truth**. This separation provides both high performance and data durability.
