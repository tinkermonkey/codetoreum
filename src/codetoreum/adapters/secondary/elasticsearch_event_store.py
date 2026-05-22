"""Elasticsearch event store adapter for production persistence."""

import logging
from collections.abc import AsyncIterator
from datetime import datetime
from typing import Any

from elasticsearch import AsyncElasticsearch
from elasticsearch.exceptions import (
    ApiError,
    AuthenticationException,
    ConnectionError,
    ConnectionTimeout,
    NotFoundError,
)

from codetoreum.domain.events.adapter_events import CodetoreumEvent
from codetoreum.infrastructure.event_serialization import EventSerializer
from codetoreum.ports.exceptions import (
    ConcurrencyConflictError,
    EventStoreError,
    ResourceNotFoundError,
)
from codetoreum.ports.output.event_store import IEventStore

logger = logging.getLogger(__name__)


class ElasticsearchEventStore(IEventStore):
    """
    Production event store using Elasticsearch.

    Features:
    - Monthly index rollover (events-YYYY.MM pattern)
    - Efficient querying by aggregate ID, timestamp, event type
    - Optimistic concurrency control using version field
    - Index lifecycle management (ILM) for retention
    - Bulk operations for performance
    - Full-text search capabilities

    Index mapping:
    {
      "event_id": keyword,
      "aggregate_id": keyword,
      "aggregate_type": keyword,
      "event_type": keyword,
      "event_version": integer,
      "timestamp": date,
      "stream_version": long,
      "correlation_id": keyword,
      "causation_id": keyword,
      "user_id": keyword,
      "data": object (enabled),
      "metadata": object
    }

    **Resilience Patterns**:
    This adapter should be wrapped with resilience decorators at instantiation:
    - Circuit breaker: Prevents cascading failures
    - Rate limiting: Controls request rate to Elasticsearch
    - Retry policy: Handles transient failures
    - Timeout: Prevents indefinite waits

    Example:
        ```python
        from codetoreum.infrastructure.resilience.factory import create_resilient_adapter

        event_store = create_resilient_adapter(
            adapter=ElasticsearchEventStore(es_client),
            adapter_type="event_store",
            config={
                "circuit_breaker": {"failure_threshold": 5},
                "retry": {"max_attempts": 3},
                "rate_limit": {"requests_per_second": 100},
                "timeout": {"seconds": 30}
            }
        )
        ```

    The adapter itself remains pure without embedded resilience logic, following
    the project's hexagonal architecture principles.
    """

    def __init__(
        self,
        es_client: AsyncElasticsearch,
        index_prefix: str = "events",
        create_index_template: bool = True,
        batch_size_limit: int = 10000,
        shard_count: int = 2,
        replica_count: int = 1,
    ):
        """
        Initialize Elasticsearch event store.

        Args:
            es_client: AsyncElasticsearch client
            index_prefix: Prefix for event indices (default: "events")
            create_index_template: Whether to create index template on init
            batch_size_limit: Maximum events per stream query (configurable)
            shard_count: Number of shards for indices (configurable)
            replica_count: Number of replicas for indices (configurable)
        """
        self.client = es_client
        self.index_prefix = index_prefix
        self._initialized = False
        self._create_index_template = create_index_template
        self.batch_size_limit = batch_size_limit
        self.shard_count = shard_count
        self.replica_count = replica_count

    async def initialize(self) -> None:
        """
        Initialize the event store (create index template).

        Raises:
            EventStoreError: If initialization fails
        """
        if self._initialized:
            return

        if self._create_index_template:
            try:
                await self._create_index_template_if_not_exists()
                self._initialized = True
                logger.info(f"Elasticsearch event store initialized with prefix '{self.index_prefix}'")
            except Exception as e:
                msg = f"Failed to initialize event store: {e}"
                raise EventStoreError(msg) from e

    async def append(
        self,
        stream_id: str,
        events: list[CodetoreumEvent],
        expected_version: int | None = None,
    ) -> None:
        """
        Append events to a stream.

        Args:
            stream_id: Event stream identifier (aggregate ID)
            events: Events to append
            expected_version: Expected current version for optimistic concurrency

        Raises:
            ConcurrencyConflictError: Version mismatch
            EventStoreError: Persistence failure
        """
        if not events:
            return

        if not self._initialized:
            await self.initialize()

        try:
            # Check current version if expected version provided
            if expected_version is not None:
                current_version = await self.get_stream_version(stream_id)
                if current_version != expected_version:
                    msg = (
                        f"Stream {stream_id}: expected version {expected_version}, "
                        f"but current version is {current_version}"
                    )
                    raise ConcurrencyConflictError(msg)

            # Get starting version for new events
            start_version = await self.get_stream_version(stream_id)

            # Prepare bulk request
            bulk_body = []
            for i, event in enumerate(events):
                stream_version = start_version + i + 1
                index_name = self._get_index_name(event.occurred_at)

                # Index operation
                bulk_body.append({"index": {"_index": index_name, "_id": str(event.event_id)}})

                # Document
                doc = EventSerializer.to_dict(event)
                doc["stream_version"] = stream_version
                doc["aggregate_id"] = stream_id
                doc["aggregate_type"] = "unknown"  # Will be set from event data if available
                bulk_body.append(doc)

            # Execute bulk insert
            response = await self.client.bulk(operations=bulk_body, refresh="wait_for")

            # Check for errors
            if response.get("errors"):
                errors = [item for item in response["items"] if "error" in item.get("index", {})]
                msg = f"Bulk insert had {len(errors)} errors: {errors[0] if errors else 'unknown'}"
                raise EventStoreError(msg)

            logger.debug(
                f"Appended {len(events)} events to stream {stream_id} "
                f"(versions {start_version + 1} to {start_version + len(events)})"
            )

        except ConcurrencyConflictError:
            raise
        except Exception as e:
            msg = f"Failed to append events: {e}"
            raise EventStoreError(msg) from e

    async def get_events(
        self,
        stream_id: str,
        from_version: int = 0,
        to_version: int | None = None,
    ) -> list[CodetoreumEvent]:
        """
        Get events from a stream.

        Args:
            stream_id: Event stream identifier
            from_version: Start from this version (inclusive)
            to_version: End at this version (inclusive), or None for all

        Returns:
            List of domain events in order

        Raises:
            ResourceNotFoundError: Stream doesn't exist
            EventStoreError: Retrieval failure
        """
        if not self._initialized:
            await self.initialize()

        try:
            # Build query
            query = {
                "bool": {
                    "must": [
                        {"term": {"aggregate_id": stream_id}},
                        {"range": {"stream_version": {"gte": from_version}}},
                    ]
                }
            }

            if to_version is not None:
                query["bool"]["must"].append({"range": {"stream_version": {"lte": to_version}}})

            # Search across all event indices
            response = await self.client.search(
                index=f"{self.index_prefix}-*",
                query=query,
                sort=[{"stream_version": "asc"}],
                size=self.batch_size_limit,  # Max events per stream (configurable)
            )

            hits = response["hits"]["hits"]

            if not hits:
                # Check if stream exists
                if from_version == 0:
                    # No events yet, that's ok
                    return []
                # Stream should exist but doesn't
                msg = "Stream"
                raise ResourceNotFoundError(msg, stream_id)

            # Convert to domain events
            events = [EventSerializer.from_dict(hit["_source"]) for hit in hits]

            return events

        except ResourceNotFoundError:
            raise
        except Exception as e:
            msg = f"Failed to get events: {e}"
            raise EventStoreError(msg) from e

    async def get_events_since(
        self,
        since: datetime,
        stream_id: str | None = None,
    ) -> list[CodetoreumEvent]:
        """
        Get events since a timestamp.

        Args:
            since: Return events after this timestamp
            stream_id: Optional stream filter

        Returns:
            List of domain events

        Raises:
            EventStoreError: Retrieval failure
        """
        if not self._initialized:
            await self.initialize()

        try:
            # Build query
            query = {"bool": {"must": [{"range": {"timestamp": {"gt": since.isoformat()}}}]}}

            if stream_id:
                query["bool"]["must"].append({"term": {"aggregate_id": stream_id}})

            # Search
            response = await self.client.search(
                index=f"{self.index_prefix}-*",
                query=query,
                sort=[{"timestamp": "asc"}],
                size=10000,
            )

            hits = response["hits"]["hits"]

            # Convert to domain events
            events = [EventSerializer.from_dict(hit["_source"]) for hit in hits]

            return events

        except Exception as e:
            msg = f"Failed to get events since: {e}"
            raise EventStoreError(msg) from e

    async def stream_events(
        self,
        stream_id: str | None = None,
        from_version: int = 0,
    ) -> AsyncIterator[CodetoreumEvent]:
        """
        Stream events in real-time.

        Note: This implementation returns existing events. For true real-time
        streaming, integrate with Redis pub/sub or EventBus.

        Args:
            stream_id: Optional stream filter
            from_version: Start from this version

        Yields:
            Domain events

        Raises:
            EventStoreError: Streaming failure
        """
        if not self._initialized:
            await self.initialize()

        try:
            # Get existing events
            if stream_id:
                events = await self.get_events(stream_id, from_version)
            else:
                # Get all events from all streams
                events = await self._get_all_events(from_version)

            for event in events:
                yield event

        except Exception as e:
            msg = f"Failed to stream events: {e}"
            raise EventStoreError(msg) from e

    async def get_stream_version(self, stream_id: str) -> int:
        """
        Get current version of a stream.

        Args:
            stream_id: Event stream identifier

        Returns:
            Current version (0 if stream doesn't exist)

        Raises:
            EventStoreError: Query failure
        """
        if not self._initialized:
            await self.initialize()

        try:
            # Query for max stream_version
            response = await self.client.search(
                index=f"{self.index_prefix}-*",
                query={"term": {"aggregate_id": stream_id}},
                size=0,  # We only want the aggregation
                aggs={"max_version": {"max": {"field": "stream_version"}}},
            )

            # Handle case where aggregations might not exist (e.g., no matching indices)
            aggs = response.get("aggregations", {})
            if not aggs or "max_version" not in aggs:
                return 0

            max_version = aggs["max_version"].get("value")

            if max_version is None:
                return 0

            return int(max_version)

        except Exception as e:
            msg = f"Failed to get stream version: {e}"
            raise EventStoreError(msg) from e

    async def stream_exists(self, stream_id: str) -> bool:
        """
        Check if a stream exists.

        Args:
            stream_id: Event stream identifier

        Returns:
            True if stream exists

        Raises:
            EventStoreError: Query failure
        """
        if not self._initialized:
            await self.initialize()

        try:
            response = await self.client.count(
                index=f"{self.index_prefix}-*",
                query={"term": {"aggregate_id": stream_id}},
            )

            return response["count"] > 0

        except Exception as e:
            msg = f"Failed to check stream existence: {e}"
            raise EventStoreError(msg) from e

    async def save_snapshot(
        self,
        stream_id: str,
        version: int,
        snapshot: dict[str, Any],
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
        # Snapshots could be stored in a separate index: snapshots-{prefix}
        # For now, we'll skip snapshot implementation
        # TODO: Implement snapshot support

    async def get_latest_snapshot(
        self,
        stream_id: str,
    ) -> dict[str, Any] | None:
        """
        Get most recent snapshot.

        Args:
            stream_id: Event stream identifier

        Returns:
            Snapshot data or None

        Raises:
            EventStoreError: Snapshot retrieval failure
        """
        # TODO: Implement snapshot support
        return None

    async def delete_stream(self, stream_id: str) -> None:
        """
        Delete an event stream.

        Args:
            stream_id: Event stream identifier

        Raises:
            ResourceNotFoundError: Stream doesn't exist
            EventStoreError: Delete operation failed
        """
        if not self._initialized:
            await self.initialize()

        try:
            # Check if stream exists
            if not await self.stream_exists(stream_id):
                msg = "Stream"
                raise ResourceNotFoundError(msg, stream_id)

            # Delete by query
            response = await self.client.delete_by_query(
                index=f"{self.index_prefix}-*",
                query={"term": {"aggregate_id": stream_id}},
                refresh=True,
            )

            deleted_count = response.get("deleted", 0)
            logger.info(f"Deleted stream {stream_id} ({deleted_count} events)")

        except ResourceNotFoundError:
            raise
        except Exception as e:
            msg = f"Failed to delete stream: {e}"
            raise EventStoreError(msg) from e

    async def get_all_stream_ids(
        self,
        aggregate_type: str | None = None,
    ) -> list[str]:
        """
        Get all stream IDs.

        Args:
            aggregate_type: Optional filter by aggregate type

        Returns:
            List of stream IDs

        Raises:
            EventStoreError: Query failure
        """
        if not self._initialized:
            await self.initialize()

        try:
            # Build query
            query: dict[str, Any] = {"match_all": {}}

            if aggregate_type:
                query = {"term": {"aggregate_type": aggregate_type}}

            # Aggregate unique aggregate_ids
            response = await self.client.search(
                index=f"{self.index_prefix}-*",
                query=query,
                size=0,
                aggs={"unique_streams": {"terms": {"field": "aggregate_id", "size": 10000}}},
            )

            aggs = response.get("aggregations", {})
            if not aggs or "unique_streams" not in aggs:
                return []

            buckets = aggs["unique_streams"].get("buckets", [])
            stream_ids = [bucket["key"] for bucket in buckets]

            return stream_ids

        except Exception as e:
            msg = f"Failed to get stream IDs: {e}"
            raise EventStoreError(msg) from e

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
        Query stream IDs by analyzing their latest events with filtering at DB level.

        This method uses Elasticsearch aggregations to efficiently filter and sort
        workflows without loading all events into memory. It groups events by
        aggregate_id and examines the latest event for each stream.

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
            EventStoreError: Query failure

        Example:
            # Get workflows with status "completed", sorted by completion time
            stream_ids, total = await event_store.query_streams_by_latest_event(
                aggregate_type="Workflow",
                event_data_filters={"data.status": "completed"},
                sort_by="timestamp",
                offset=0,
                limit=20
            )
        """
        if not self._initialized:
            await self.initialize()

        try:
            # Build query
            must_clauses = [{"term": {"aggregate_type": aggregate_type}}]

            if event_type_filters:
                must_clauses.append({"terms": {"event_type": event_type_filters}})

            if event_data_filters:
                for field, value in event_data_filters.items():
                    if isinstance(value, list):
                        # For lists, use terms query (OR logic)
                        must_clauses.append({"terms": {field: value}})
                    else:
                        must_clauses.append({"term": {field: value}})

            query = {"bool": {"must": must_clauses}}

            # Build aggregation - get latest event per stream with composite agg
            # This allows efficient pagination through streams
            agg_body = {
                "streams": {
                    "composite": {
                        "size": limit,
                        "sources": [{"aggregate_id": {"terms": {"field": "aggregate_id"}}}],
                    },
                    "aggregations": {
                        "latest_event": {
                            "top_hits": {
                                "size": 1,
                                "sort": [{"stream_version": "desc"}],
                                "_source": ["aggregate_id", "timestamp", "stream_version"],
                            }
                        }
                    },
                }
            }

            # For offset support with composite aggregation, we need to paginate
            # through buckets. This is more complex but necessary for proper pagination.
            all_streams = []
            after_key = None
            collected = 0
            skipped = 0

            while collected < offset + limit:
                if after_key:
                    agg_body["streams"]["composite"]["after"] = after_key

                response = await self.client.search(
                    index=f"{self.index_prefix}-*",
                    query=query,
                    size=0,
                    aggs=agg_body,
                )

                aggs = response.get("aggregations", {})
                if not aggs or "streams" not in aggs:
                    break

                buckets = aggs["streams"].get("buckets", [])
                if not buckets:
                    break

                for bucket in buckets:
                    if skipped < offset:
                        skipped += 1
                        continue

                    if collected >= offset + limit:
                        break

                    stream_id = bucket["key"]["aggregate_id"]
                    all_streams.append(stream_id)
                    collected += 1

                # Check if there are more results
                after_key = aggs["streams"].get("after_key")
                if not after_key:
                    break

            # Get total count (separate query for accuracy)
            count_response = await self.client.search(
                index=f"{self.index_prefix}-*",
                query=query,
                size=0,
                aggs={"unique_streams": {"cardinality": {"field": "aggregate_id"}}},
            )
            count_aggs = count_response.get("aggregations", {})
            if not count_aggs or "unique_streams" not in count_aggs:
                total_count = 0
            else:
                total_count = int(count_aggs["unique_streams"]["value"])

            return all_streams, total_count

        except Exception as e:
            msg = f"Failed to query streams by latest event: {e}"
            raise EventStoreError(msg) from e

    async def get_events_by_type(
        self,
        event_type: str,
        since: datetime | None = None,
        limit: int = 1000,
    ) -> list[CodetoreumEvent]:
        """
        Get events by event type.

        Args:
            event_type: Event type name
            since: Optional timestamp filter
            limit: Maximum number of events to return

        Returns:
            List of matching events

        Raises:
            EventStoreError: Query failure
        """
        if not self._initialized:
            await self.initialize()

        try:
            # Build query
            query = {"bool": {"must": [{"term": {"event_type": event_type}}]}}

            if since:
                query["bool"]["must"].append({"range": {"timestamp": {"gte": since.isoformat()}}})

            # Search
            response = await self.client.search(
                index=f"{self.index_prefix}-*",
                query=query,
                sort=[{"timestamp": "desc"}],
                size=limit,
            )

            hits = response["hits"]["hits"]

            # Convert to domain events
            events = [EventSerializer.from_dict(hit["_source"]) for hit in hits]

            return events

        except Exception as e:
            msg = f"Failed to get events by type: {e}"
            raise EventStoreError(msg) from e

    async def get_events_by_correlation_id(
        self,
        correlation_id: str,
    ) -> list[CodetoreumEvent]:
        """
        Get all events with a specific correlation ID.

        Args:
            correlation_id: Correlation ID to search for

        Returns:
            List of correlated events

        Raises:
            EventStoreError: Query failure
        """
        if not self._initialized:
            await self.initialize()

        try:
            response = await self.client.search(
                index=f"{self.index_prefix}-*",
                query={"term": {"correlation_id": correlation_id}},
                sort=[{"timestamp": "asc"}],
                size=10000,
            )

            hits = response["hits"]["hits"]

            # Convert to domain events
            events = [EventSerializer.from_dict(hit["_source"]) for hit in hits]

            return events

        except Exception as e:
            msg = f"Failed to get events by correlation ID: {e}"
            raise EventStoreError(msg) from e

    async def replay_events(
        self,
        stream_id: str,
        from_version: int = 0,
        to_version: int | None = None,
    ) -> AsyncIterator[CodetoreumEvent]:
        """
        Replay events from a stream for debugging/recovery.

        Args:
            stream_id: Event stream identifier
            from_version: Start from this version
            to_version: End at this version (None for all)

        Yields:
            Domain events in order

        Raises:
            ResourceNotFoundError: Stream doesn't exist
            EventStoreError: Replay failure
        """
        if not self._initialized:
            await self.initialize()

        try:
            events = await self.get_events(stream_id, from_version, to_version)

            if not events and from_version == 0:
                msg = "Stream"
                raise ResourceNotFoundError(msg, stream_id)

            for event in events:
                yield event

        except ResourceNotFoundError:
            raise
        except Exception as e:
            msg = f"Failed to replay events: {e}"
            raise EventStoreError(msg) from e

    async def get_statistics(self) -> dict[str, Any]:
        """
        Get event store statistics.

        Returns:
            Dictionary with statistics (total events, streams, etc.)

        Raises:
            EventStoreError: Query failure
        """
        if not self._initialized:
            await self.initialize()

        try:
            # Total events
            total_response = await self.client.count(index=f"{self.index_prefix}-*")
            total_events = total_response["count"]

            # Unique streams
            streams_response = await self.client.search(
                index=f"{self.index_prefix}-*",
                size=0,
                aggs={"unique_streams": {"cardinality": {"field": "aggregate_id"}}},
            )
            streams_aggs = streams_response.get("aggregations", {})
            total_streams = 0
            if streams_aggs and "unique_streams" in streams_aggs:
                total_streams = streams_aggs["unique_streams"]["value"]

            # Events by type
            types_response = await self.client.search(
                index=f"{self.index_prefix}-*",
                size=0,
                aggs={"event_types": {"terms": {"field": "event_type", "size": 100}}},
            )
            types_aggs = types_response.get("aggregations", {})
            events_by_type = {}
            if types_aggs and "event_types" in types_aggs:
                events_by_type = {
                    bucket["key"]: bucket["doc_count"] for bucket in types_aggs["event_types"].get("buckets", [])
                }

            return {
                "total_events": total_events,
                "total_streams": total_streams,
                "events_by_type": events_by_type,
                "index_prefix": self.index_prefix,
            }

        except Exception as e:
            msg = f"Failed to get statistics: {e}"
            raise EventStoreError(msg) from e

    # Helper methods

    def _get_index_name(self, timestamp: datetime) -> str:
        """
        Generate index name with monthly rollover.

        Args:
            timestamp: Event timestamp

        Returns:
            Index name (e.g., "events-2025.10")
        """
        return f"{self.index_prefix}-{timestamp.strftime('%Y.%m')}"

    async def _get_all_events(self, from_version: int = 0) -> list[CodetoreumEvent]:
        """
        Get all events across all streams.

        Args:
            from_version: Minimum stream version

        Returns:
            List of domain events
        """
        response = await self.client.search(
            index=f"{self.index_prefix}-*",
            query={"range": {"stream_version": {"gte": from_version}}},
            sort=[{"timestamp": "asc"}],
            size=10000,
        )

        hits = response["hits"]["hits"]
        events = [EventSerializer.from_dict(hit["_source"]) for hit in hits]

        return events

    async def _create_index_template_if_not_exists(self) -> None:
        """Create index template for event indices."""
        template_name = f"{self.index_prefix}-template"

        # Check if template exists
        try:
            exists = await self.client.indices.exists_index_template(name=template_name)
            if exists:
                logger.debug(f"Index template '{template_name}' already exists")
                return
        except NotFoundError:
            # Template doesn't exist, will create it below
            pass
        except (ConnectionError, ConnectionTimeout, AuthenticationException) as e:
            # Infrastructure failure - propagate as EventStoreError
            msg = f"Failed to check if index template exists: {e}"
            logger.error(msg, exc_info=True)
            raise EventStoreError(msg) from e
        except ApiError as e:
            # Other API errors (permissions, service unavailable, etc.)
            msg = f"Failed to check if index template exists (API error {e.status_code}): {e}"
            logger.error(msg, exc_info=True)
            raise EventStoreError(msg) from e

        # Define index template
        template = {
            "index_patterns": [f"{self.index_prefix}-*"],
            "template": {
                "settings": {
                    "number_of_shards": self.shard_count,
                    "number_of_replicas": self.replica_count,
                    "refresh_interval": "5s",
                },
                "mappings": {
                    "properties": {
                        "event_id": {"type": "keyword"},
                        "aggregate_id": {"type": "keyword"},
                        "aggregate_type": {"type": "keyword"},
                        "event_type": {"type": "keyword"},
                        "event_version": {"type": "integer"},
                        "timestamp": {"type": "date"},
                        "stream_version": {"type": "long"},
                        "correlation_id": {"type": "keyword"},
                        "causation_id": {"type": "keyword"},
                        "user_id": {"type": "keyword"},
                        "data": {"type": "object", "enabled": True, "dynamic": True},
                        "metadata": {
                            "type": "object",
                            "enabled": True,
                            "dynamic": False,
                            "properties": {
                                "trace_id": {"type": "keyword"},
                                "span_id": {"type": "keyword"},
                                "service": {"type": "keyword"},
                            },
                        },
                    }
                },
            },
        }

        # Create template
        try:
            await self.client.indices.put_index_template(
                name=template_name, index_patterns=template["index_patterns"], template=template["template"]
            )
        except (ConnectionError, ConnectionTimeout, AuthenticationException) as e:
            # Infrastructure failure - propagate as EventStoreError
            msg = f"Failed to create index template: {e}"
            logger.error(msg, exc_info=True)
            raise EventStoreError(msg) from e
        except ApiError as e:
            # Other API errors (permissions, service unavailable, etc.)
            msg = f"Failed to create index template (API error {e.status_code}): {e}"
            logger.error(msg, exc_info=True)
            raise EventStoreError(msg) from e

        logger.info(f"Created index template '{template_name}'")

    async def close(self) -> None:
        """Close the event store (cleanup resources)."""
        try:
            if self.client:
                logger.info("Closing Elasticsearch client")
                await self.client.close()
        except Exception as e:
            logger.error(f"Error closing Elasticsearch client: {e}", exc_info=True)
        finally:
            self._initialized = False
            logger.info("Elasticsearch event store closed")
