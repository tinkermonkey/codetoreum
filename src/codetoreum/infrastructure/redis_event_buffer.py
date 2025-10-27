"""Redis event buffer for high-throughput event writes."""

import asyncio
import json
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from redis import asyncio as aioredis

from codetoreum.domain.events import DomainEvent
from codetoreum.infrastructure.event_serialization import EventSerializer

logger = logging.getLogger(__name__)


class RedisEventBufferError(Exception):
    """Raised when Redis event buffer operations fail."""

    pass


class RedisEventBuffer:
    """
    Buffers events in Redis Streams before Elasticsearch persistence.

    Provides:
    - High-throughput writes using Redis Streams
    - Reliable delivery via consumer groups
    - Backpressure handling
    - Dead letter queue for failed events
    - Dual-purpose: buffer for persistence AND pub/sub for real-time handlers

    Architecture:
        Application → Redis Streams → Background Workers → Elasticsearch
                           ↓
                    In-Memory Event Bus (real-time handlers)
    """

    def __init__(
        self,
        redis_client: aioredis.Redis,
        stream_name: str = "events:buffer",
        consumer_group: str = "elasticsearch-writers",
        stream_max_length: int = 100000,
        dead_letter_stream: str = "events:dead-letter",
    ):
        """
        Initialize Redis event buffer.

        Args:
            redis_client: Redis async client
            stream_name: Name of the Redis stream for events
            consumer_group: Name of the consumer group for persistence workers
            stream_max_length: Maximum stream length before trimming (MAXLEN) - configurable
            dead_letter_stream: Stream for events that fail processing
        """
        self.redis = redis_client
        self.stream_name = stream_name
        self.consumer_group = consumer_group
        self.stream_max_length = stream_max_length
        self.dead_letter_stream = dead_letter_stream

        self._initialized = False

    async def initialize(self) -> None:
        """
        Initialize the buffer (create consumer group if needed).

        Raises:
            RedisEventBufferError: If initialization fails
        """
        if self._initialized:
            return

        try:
            # Create consumer group (XGROUP CREATE)
            # Using MKSTREAM to create stream if it doesn't exist
            try:
                await self.redis.xgroup_create(
                    name=self.stream_name,
                    groupname=self.consumer_group,
                    id="0",
                    mkstream=True,
                )
                logger.info(
                    f"Created consumer group '{self.consumer_group}' "
                    f"for stream '{self.stream_name}'"
                )
            except aioredis.ResponseError as e:
                if "BUSYGROUP" in str(e):
                    # Group already exists, that's fine
                    logger.debug(
                        f"Consumer group '{self.consumer_group}' already exists"
                    )
                else:
                    raise

            self._initialized = True

        except Exception as e:
            raise RedisEventBufferError(f"Failed to initialize buffer: {e}") from e

    async def buffer_event(self, event: DomainEvent) -> str:
        """
        Write event to Redis Stream.

        Args:
            event: Domain event to buffer

        Returns:
            Message ID from Redis (e.g., "1609459200000-0")

        Raises:
            RedisEventBufferError: If buffering fails
        """
        if not self._initialized:
            await self.initialize()

        try:
            # Serialize event
            event_json = EventSerializer.serialize(event)

            # Add to stream with MAXLEN to prevent unbounded growth
            message_id = await self.redis.xadd(
                name=self.stream_name,
                fields={
                    "event_id": str(event.event_id),
                    "event_type": event.event_type,
                    "aggregate_id": event.aggregate_id,
                    "aggregate_type": event.aggregate_type,
                    "timestamp": event.occurred_at.isoformat(),
                    "payload": event_json,
                },
                maxlen=self.stream_max_length,
                approximate=True,  # Use ~ for efficiency
            )

            logger.debug(
                f"Buffered event {event.event_type} "
                f"(ID: {event.event_id}) to stream {self.stream_name} "
                f"with message ID {message_id}"
            )

            return message_id

        except Exception as e:
            raise RedisEventBufferError(f"Failed to buffer event: {e}") from e

    async def buffer_events_batch(self, events: List[DomainEvent]) -> List[str]:
        """
        Buffer multiple events efficiently using pipeline.

        Args:
            events: List of domain events to buffer

        Returns:
            List of message IDs from Redis

        Raises:
            RedisEventBufferError: If buffering fails
        """
        if not self._initialized:
            await self.initialize()

        if not events:
            return []

        try:
            # Use pipeline for batch operations
            async with self.redis.pipeline(transaction=False) as pipe:
                for event in events:
                    event_json = EventSerializer.serialize(event)

                    pipe.xadd(
                        name=self.stream_name,
                        fields={
                            "event_id": str(event.event_id),
                            "event_type": event.event_type,
                            "aggregate_id": event.aggregate_id,
                            "aggregate_type": event.aggregate_type,
                            "timestamp": event.occurred_at.isoformat(),
                            "payload": event_json,
                        },
                        maxlen=self.stream_max_length,
                        approximate=True,
                    )

                message_ids = await pipe.execute()

            logger.debug(
                f"Buffered {len(events)} events to stream {self.stream_name}"
            )

            return message_ids

        except Exception as e:
            raise RedisEventBufferError(
                f"Failed to buffer events batch: {e}"
            ) from e

    async def read_pending_events(
        self,
        consumer_name: str,
        count: int = 100,
        block_ms: int = 1000,
    ) -> List[Dict[str, Any]]:
        """
        Read pending events from stream (for background workers).

        Args:
            consumer_name: Name of this consumer (for tracking)
            count: Maximum number of events to read
            block_ms: Block for this many milliseconds if no events

        Returns:
            List of event dictionaries with 'id', 'data', and 'event' keys

        Raises:
            RedisEventBufferError: If read fails
        """
        if not self._initialized:
            await self.initialize()

        try:
            # Read from stream using consumer group (XREADGROUP)
            # '>' means "messages never delivered to any consumer"
            messages = await self.redis.xreadgroup(
                groupname=self.consumer_group,
                consumername=consumer_name,
                streams={self.stream_name: ">"},
                count=count,
                block=block_ms,
            )

            if not messages:
                return []

            # Parse messages
            events = []
            for stream_name, stream_messages in messages:
                for message_id, fields in stream_messages:
                    try:
                        # Deserialize event from payload
                        event_json = fields[b"payload"].decode("utf-8")
                        event = EventSerializer.deserialize(event_json)

                        events.append(
                            {
                                "id": message_id.decode("utf-8"),
                                "data": fields,
                                "event": event,
                            }
                        )

                    except Exception as e:
                        logger.error(
                            f"Failed to deserialize event from message {message_id}: {e}"
                        )
                        # Move to dead letter queue
                        await self._move_to_dead_letter(message_id, fields, str(e))

            return events

        except Exception as e:
            raise RedisEventBufferError(f"Failed to read events: {e}") from e

    async def acknowledge_events(
        self, message_ids: List[str]
    ) -> int:
        """
        Acknowledge successful processing of events (XACK).

        Args:
            message_ids: List of Redis message IDs to acknowledge

        Returns:
            Number of messages acknowledged

        Raises:
            RedisEventBufferError: If acknowledgment fails
        """
        if not message_ids:
            return 0

        try:
            count = await self.redis.xack(
                self.stream_name,
                self.consumer_group,
                *message_ids,
            )

            logger.debug(f"Acknowledged {count} events in stream {self.stream_name}")

            return count

        except Exception as e:
            raise RedisEventBufferError(f"Failed to acknowledge events: {e}") from e

    async def get_pending_count(self, consumer_name: Optional[str] = None) -> int:
        """
        Get count of pending (unacknowledged) events.

        Args:
            consumer_name: Optional consumer name to filter by

        Returns:
            Number of pending events

        Raises:
            RedisEventBufferError: If query fails
        """
        try:
            # XPENDING command
            pending_info = await self.redis.xpending(
                self.stream_name,
                self.consumer_group,
            )

            if pending_info is None:
                return 0

            # pending_info format: [count, start_id, end_id, consumers]
            return pending_info[0] if isinstance(pending_info, list) else 0

        except Exception as e:
            raise RedisEventBufferError(f"Failed to get pending count: {e}") from e

    async def get_stream_length(self) -> int:
        """
        Get current length of the event stream.

        Returns:
            Number of events in stream

        Raises:
            RedisEventBufferError: If query fails
        """
        try:
            length = await self.redis.xlen(self.stream_name)
            return length

        except Exception as e:
            raise RedisEventBufferError(f"Failed to get stream length: {e}") from e

    async def get_buffer_stats(self) -> Dict[str, Any]:
        """
        Get buffer statistics for monitoring.

        Returns:
            Dictionary with buffer statistics

        Raises:
            RedisEventBufferError: If query fails
        """
        try:
            stream_length = await self.get_stream_length()
            pending_count = await self.get_pending_count()

            # Get stream info
            stream_info = await self.redis.xinfo_stream(self.stream_name)

            # Get consumer group info
            try:
                groups_info = await self.redis.xinfo_groups(self.stream_name)
                consumer_count = len(groups_info) if groups_info else 0
            except aioredis.ResponseError:
                consumer_count = 0

            return {
                "stream_name": self.stream_name,
                "stream_length": stream_length,
                "pending_count": pending_count,
                "consumer_count": consumer_count,
                "first_entry_id": (
                    stream_info.get("first-entry", [None])[0] if stream_info else None
                ),
                "last_entry_id": (
                    stream_info.get("last-entry", [None])[0] if stream_info else None
                ),
                "max_stream_length": self.stream_max_length,
                "utilization": (
                    stream_length / self.stream_max_length
                    if self.stream_max_length > 0
                    else 0
                ),
            }

        except Exception as e:
            raise RedisEventBufferError(f"Failed to get buffer stats: {e}") from e

    async def _move_to_dead_letter(
        self, message_id: bytes, fields: Dict[bytes, bytes], error: str
    ) -> None:
        """
        Move a failed event to the dead letter queue.

        Args:
            message_id: Original message ID
            fields: Event fields
            error: Error message
        """
        try:
            await self.redis.xadd(
                name=self.dead_letter_stream,
                fields={
                    **fields,
                    b"original_message_id": message_id,
                    b"error": error.encode("utf-8"),
                    b"moved_at": datetime.now(timezone.utc).isoformat().encode("utf-8"),
                },
            )

            logger.warning(
                f"Moved message {message_id} to dead letter queue due to error: {error}"
            )

        except Exception as e:
            logger.error(
                f"Failed to move message {message_id} to dead letter queue: {e}"
            )

    async def close(self) -> None:
        """Close the buffer (cleanup resources)."""
        # Redis client is managed externally, so nothing to do here
        self._initialized = False
        logger.info("Redis event buffer closed")
