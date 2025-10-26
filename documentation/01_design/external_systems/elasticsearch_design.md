# Elasticsearch External System - Detailed Design

## Overview

Elasticsearch provides distributed search and analytics capabilities for the Codetoreum platform. This external system is responsible for event indexing, metrics storage, historical analysis, and configuration persistence. This document details the abstraction layer, indexing strategies, and mock implementations.

## System Purpose

**Primary Functions**:
1. Event and decision tracking with searchable history
2. Metrics collection and aggregation
3. Pattern detection and anomaly analysis
4. Configuration storage (moving from YAML)
5. Full-text search capabilities
6. Time-series data analysis
7. Debugging and troubleshooting support

## Port Interface Design

### IEventStore Interface

```python
from abc import ABC, abstractmethod
from typing import List, Dict, Optional, Any
from dataclasses import dataclass
from datetime import datetime
from enum import Enum

class EventType(Enum):
    """Types of events tracked."""
    TASK_RECEIVED = "task_received"
    AGENT_INITIALIZED = "agent_initialized"
    AGENT_STARTED = "agent_started"
    AGENT_COMPLETED = "agent_completed"
    AGENT_FAILED = "agent_failed"
    DECISION = "decision"
    METRIC = "metric"

@dataclass
class Event:
    """A trackable event."""
    id: str                          # Unique event ID
    timestamp: datetime              # When event occurred
    event_type: EventType            # Type of event
    agent: str                       # Agent involved
    task_id: str                     # Task identifier
    project: str                     # Project name
    data: Dict[str, Any]             # Event-specific data
    pipeline_run_id: Optional[str] = None

@dataclass
class Metric:
    """A performance or quality metric."""
    id: str
    timestamp: datetime
    metric_name: str                 # Metric identifier
    metric_type: str                 # 'task' or 'quality'
    value: float                     # Metric value
    unit: str                        # Unit of measurement
    tags: Dict[str, str]             # Metadata tags
    project: str
    agent: Optional[str] = None

@dataclass
class SearchQuery:
    """Query for searching events."""
    query: str                       # Search query (Lucene syntax)
    filters: Dict[str, Any]          # Field filters
    start_time: Optional[datetime]   # Time range start
    end_time: Optional[datetime]     # Time range end
    size: int = 100                  # Max results
    sort_by: str = "timestamp"       # Sort field
    sort_order: str = "desc"         # 'asc' or 'desc'

class IEventStore(ABC):
    """
    Port interface for event storage and search.

    Abstracts Elasticsearch, database, and in-memory storage.
    """

    @abstractmethod
    async def store_event(self, event: Event) -> str:
        """
        Store an event.

        Args:
            event: Event to store

        Returns:
            Event ID
        """
        pass

    @abstractmethod
    async def store_events_bulk(self, events: List[Event]) -> List[str]:
        """
        Store multiple events efficiently.

        Returns:
            List of event IDs
        """
        pass

    @abstractmethod
    async def get_event(self, event_id: str) -> Optional[Event]:
        """Retrieve event by ID."""
        pass

    @abstractmethod
    async def search_events(
        self,
        query: SearchQuery
    ) -> List[Event]:
        """
        Search events with query.

        Returns:
            List of matching events
        """
        pass

    @abstractmethod
    async def count_events(
        self,
        filters: Dict[str, Any],
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None
    ) -> int:
        """Count events matching filters."""
        pass

    @abstractmethod
    async def aggregate_events(
        self,
        aggregation_name: str,
        field: str,
        filters: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Aggregate events by field.

        Examples:
        - Count by agent
        - Average duration by project
        - Unique projects per day
        """
        pass

    @abstractmethod
    async def store_metric(self, metric: Metric) -> str:
        """Store a metric."""
        pass

    @abstractmethod
    async def get_metrics(
        self,
        metric_name: str,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        tags: Optional[Dict[str, str]] = None
    ) -> List[Metric]:
        """Retrieve metrics with filtering."""
        pass
```

### IConfigStore Interface

```python
@dataclass
class ConfigDocument:
    """A configuration document."""
    id: str
    config_type: str                 # 'workflow', 'pipeline', 'agent', 'review_filter'
    name: str                        # Config name
    version: int                     # Version number
    data: Dict[str, Any]             # Configuration data
    created_at: datetime
    updated_at: datetime
    created_by: str
    is_active: bool = True

class IConfigStore(ABC):
    """
    Port interface for configuration storage.

    Replaces YAML files with database storage.
    """

    @abstractmethod
    async def save_config(self, config: ConfigDocument) -> str:
        """
        Save configuration.

        Creates new version if config already exists.

        Returns:
            Config ID
        """
        pass

    @abstractmethod
    async def get_config(
        self,
        config_type: str,
        name: str,
        version: Optional[int] = None
    ) -> Optional[ConfigDocument]:
        """
        Retrieve configuration.

        Args:
            config_type: Type of config
            name: Config name
            version: Specific version (None = latest)
        """
        pass

    @abstractmethod
    async def list_configs(
        self,
        config_type: str,
        active_only: bool = True
    ) -> List[ConfigDocument]:
        """List all configurations of a type."""
        pass

    @abstractmethod
    async def update_config(
        self,
        config_id: str,
        data: Dict[str, Any],
        updated_by: str
    ) -> ConfigDocument:
        """
        Update configuration (creates new version).

        Returns:
            Updated config with new version
        """
        pass

    @abstractmethod
    async def deactivate_config(self, config_id: str) -> None:
        """Mark configuration as inactive."""
        pass
```

## Production Adapter: ElasticsearchAdapter

### Implementation Structure

```python
from elasticsearch import AsyncElasticsearch
from datetime import datetime, timedelta
import uuid

class ElasticsearchEventStore(IEventStore):
    """
    Production adapter for Elasticsearch event storage.

    Uses daily indices for automatic rollover.
    """

    def __init__(
        self,
        es_host: str = "localhost",
        es_port: int = 9200,
        username: Optional[str] = None,
        password: Optional[str] = None
    ):
        """
        Initialize Elasticsearch adapter.

        Args:
            es_host: Elasticsearch hostname
            es_port: Elasticsearch port
            username: Optional username for auth
            password: Optional password for auth
        """
        if username and password:
            self.client = AsyncElasticsearch(
                hosts=[f"http://{es_host}:{es_port}"],
                basic_auth=(username, password)
            )
        else:
            self.client = AsyncElasticsearch(
                hosts=[f"http://{es_host}:{es_port}"]
            )

    async def store_event(self, event: Event) -> str:
        """Store event in daily index."""
        index_name = self._get_index_name(event.event_type, event.timestamp)

        doc = {
            'timestamp': event.timestamp.isoformat(),
            'event_type': event.event_type.value,
            'agent': event.agent,
            'task_id': event.task_id,
            'project': event.project,
            'pipeline_run_id': event.pipeline_run_id,
            **event.data
        }

        result = await self.client.index(
            index=index_name,
            id=event.id,
            document=doc
        )

        return result['_id']

    async def store_events_bulk(self, events: List[Event]) -> List[str]:
        """Bulk store events for better performance."""
        bulk_body = []

        for event in events:
            index_name = self._get_index_name(event.event_type, event.timestamp)

            # Index action
            bulk_body.append({
                'index': {
                    '_index': index_name,
                    '_id': event.id
                }
            })

            # Document
            bulk_body.append({
                'timestamp': event.timestamp.isoformat(),
                'event_type': event.event_type.value,
                'agent': event.agent,
                'task_id': event.task_id,
                'project': event.project,
                'pipeline_run_id': event.pipeline_run_id,
                **event.data
            })

        response = await self.client.bulk(body=bulk_body)

        # Extract IDs from response
        ids = [item['index']['_id'] for item in response['items']]
        return ids

    async def search_events(
        self,
        query: SearchQuery
    ) -> List[Event]:
        """Search events using Elasticsearch query."""
        # Build query
        es_query = {
            'bool': {
                'must': []
            }
        }

        # Add text query if provided
        if query.query:
            es_query['bool']['must'].append({
                'query_string': {
                    'query': query.query
                }
            })

        # Add filters
        for field, value in query.filters.items():
            es_query['bool']['must'].append({
                'term': {field: value}
            })

        # Add time range
        if query.start_time or query.end_time:
            time_range = {}
            if query.start_time:
                time_range['gte'] = query.start_time.isoformat()
            if query.end_time:
                time_range['lte'] = query.end_time.isoformat()

            es_query['bool']['must'].append({
                'range': {
                    'timestamp': time_range
                }
            })

        # Determine index pattern
        index_pattern = self._get_index_pattern(query.start_time, query.end_time)

        # Execute search
        response = await self.client.search(
            index=index_pattern,
            query=es_query,
            size=query.size,
            sort=[{query.sort_by: query.sort_order}]
        )

        # Convert results to Event objects
        events = []
        for hit in response['hits']['hits']:
            source = hit['_source']

            event = Event(
                id=hit['_id'],
                timestamp=datetime.fromisoformat(source['timestamp']),
                event_type=EventType(source['event_type']),
                agent=source['agent'],
                task_id=source['task_id'],
                project=source['project'],
                pipeline_run_id=source.get('pipeline_run_id'),
                data={k: v for k, v in source.items()
                      if k not in ['timestamp', 'event_type', 'agent',
                                   'task_id', 'project', 'pipeline_run_id']}
            )
            events.append(event)

        return events

    async def aggregate_events(
        self,
        aggregation_name: str,
        field: str,
        filters: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Perform aggregation on events."""
        # Build query
        query = {'match_all': {}}
        if filters:
            query = {
                'bool': {
                    'must': [
                        {'term': {k: v}} for k, v in filters.items()
                    ]
                }
            }

        # Build aggregation
        aggs = {
            aggregation_name: {
                'terms': {
                    'field': f"{field}.keyword",  # Use keyword field
                    'size': 100
                }
            }
        }

        # Execute
        response = await self.client.search(
            index="*-events-*",
            query=query,
            aggs=aggs,
            size=0  # Don't return documents
        )

        return response['aggregations'][aggregation_name]

    def _get_index_name(
        self,
        event_type: EventType,
        timestamp: datetime
    ) -> str:
        """Generate index name with date suffix."""
        date_suffix = timestamp.strftime("%Y-%m-%d")

        if event_type == EventType.DECISION:
            return f"decision-events-{date_suffix}"
        elif event_type == EventType.METRIC:
            return f"metrics-{date_suffix}"
        else:
            return f"agent-events-{date_suffix}"

    def _get_index_pattern(
        self,
        start_time: Optional[datetime],
        end_time: Optional[datetime]
    ) -> str:
        """Generate index pattern for search."""
        if not start_time and not end_time:
            return "*-events-*"

        # For date ranges, search all indices
        # Elasticsearch will filter by timestamp
        return "*-events-*"


class ElasticsearchConfigStore(IConfigStore):
    """Elasticsearch-based configuration storage."""

    def __init__(
        self,
        es_host: str = "localhost",
        es_port: int = 9200,
        username: Optional[str] = None,
        password: Optional[str] = None
    ):
        if username and password:
            self.client = AsyncElasticsearch(
                hosts=[f"http://{es_host}:{es_port}"],
                basic_auth=(username, password)
            )
        else:
            self.client = AsyncElasticsearch(
                hosts=[f"http://{es_host}:{es_port}"]
            )

        self.config_index = "platform-config"

    async def save_config(self, config: ConfigDocument) -> str:
        """Save configuration to Elasticsearch."""
        # Check if config exists
        existing = await self.get_config(
            config.config_type,
            config.name
        )

        if existing:
            # Increment version
            config.version = existing.version + 1
        else:
            config.version = 1

        config.id = f"{config.config_type}-{config.name}-v{config.version}"
        config.updated_at = datetime.utcnow()

        doc = {
            'config_type': config.config_type,
            'name': config.name,
            'version': config.version,
            'data': config.data,
            'created_at': config.created_at.isoformat(),
            'updated_at': config.updated_at.isoformat(),
            'created_by': config.created_by,
            'is_active': config.is_active
        }

        await self.client.index(
            index=self.config_index,
            id=config.id,
            document=doc
        )

        return config.id

    async def get_config(
        self,
        config_type: str,
        name: str,
        version: Optional[int] = None
    ) -> Optional[ConfigDocument]:
        """Retrieve configuration."""
        # Build query
        query = {
            'bool': {
                'must': [
                    {'term': {'config_type': config_type}},
                    {'term': {'name.keyword': name}},
                    {'term': {'is_active': True}}
                ]
            }
        }

        if version:
            query['bool']['must'].append({'term': {'version': version}})

        # Search
        response = await self.client.search(
            index=self.config_index,
            query=query,
            sort=[{'version': 'desc'}],
            size=1
        )

        if not response['hits']['hits']:
            return None

        hit = response['hits']['hits'][0]
        source = hit['_source']

        return ConfigDocument(
            id=hit['_id'],
            config_type=source['config_type'],
            name=source['name'],
            version=source['version'],
            data=source['data'],
            created_at=datetime.fromisoformat(source['created_at']),
            updated_at=datetime.fromisoformat(source['updated_at']),
            created_by=source['created_by'],
            is_active=source['is_active']
        )
```

## Mock Adapter: InMemoryEventStore

```python
from collections import defaultdict

class InMemoryEventStore(IEventStore):
    """Mock event store using in-memory storage."""

    def __init__(self):
        self.events: Dict[str, Event] = {}
        self.metrics: Dict[str, Metric] = {}

    async def store_event(self, event: Event) -> str:
        """Store event in memory."""
        if not event.id:
            event.id = str(uuid.uuid4())

        self.events[event.id] = event
        return event.id

    async def store_events_bulk(self, events: List[Event]) -> List[str]:
        """Bulk store events."""
        ids = []
        for event in events:
            event_id = await self.store_event(event)
            ids.append(event_id)
        return ids

    async def get_event(self, event_id: str) -> Optional[Event]:
        """Retrieve event."""
        return self.events.get(event_id)

    async def search_events(
        self,
        query: SearchQuery
    ) -> List[Event]:
        """Search events in memory."""
        results = list(self.events.values())

        # Apply filters
        for field, value in query.filters.items():
            results = [
                e for e in results
                if self._match_filter(e, field, value)
            ]

        # Apply time range
        if query.start_time:
            results = [e for e in results if e.timestamp >= query.start_time]

        if query.end_time:
            results = [e for e in results if e.timestamp <= query.end_time]

        # Apply text query (simple substring match)
        if query.query:
            results = [
                e for e in results
                if self._match_text(e, query.query)
            ]

        # Sort
        reverse = query.sort_order == 'desc'
        results.sort(
            key=lambda e: getattr(e, query.sort_by, e.timestamp),
            reverse=reverse
        )

        # Limit
        return results[:query.size]

    async def count_events(
        self,
        filters: Dict[str, Any],
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None
    ) -> int:
        """Count matching events."""
        query = SearchQuery(
            query="",
            filters=filters,
            start_time=start_time,
            end_time=end_time,
            size=999999
        )

        results = await self.search_events(query)
        return len(results)

    def _match_filter(self, event: Event, field: str, value: Any) -> bool:
        """Check if event matches filter."""
        if field == 'agent':
            return event.agent == value
        elif field == 'project':
            return event.project == value
        elif field == 'event_type':
            return event.event_type.value == value
        elif field in event.data:
            return event.data[field] == value
        return False

    def _match_text(self, event: Event, query: str) -> bool:
        """Simple text matching."""
        query_lower = query.lower()

        # Check common fields
        if query_lower in event.agent.lower():
            return True
        if query_lower in event.project.lower():
            return True

        # Check data values
        for value in event.data.values():
            if isinstance(value, str) and query_lower in value.lower():
                return True

        return False


class InMemoryConfigStore(IConfigStore):
    """Mock config store."""

    def __init__(self):
        self.configs: Dict[str, ConfigDocument] = {}
        self.versions: defaultdict = defaultdict(list)

    async def save_config(self, config: ConfigDocument) -> str:
        """Save config in memory."""
        key = f"{config.config_type}:{config.name}"

        # Get version
        if key in self.versions:
            config.version = len(self.versions[key]) + 1
        else:
            config.version = 1

        config.id = f"{config.config_type}-{config.name}-v{config.version}"
        config.updated_at = datetime.utcnow()

        self.configs[config.id] = config
        self.versions[key].append(config)

        return config.id

    async def get_config(
        self,
        config_type: str,
        name: str,
        version: Optional[int] = None
    ) -> Optional[ConfigDocument]:
        """Get config."""
        key = f"{config_type}:{name}"

        if key not in self.versions:
            return None

        versions = [c for c in self.versions[key] if c.is_active]

        if not versions:
            return None

        if version:
            for config in versions:
                if config.version == version:
                    return config
            return None

        # Return latest version
        return max(versions, key=lambda c: c.version)
```

## Error Handling

```python
class ElasticsearchError(Exception):
    """Base exception for Elasticsearch operations."""
    pass

class ConnectionError(ElasticsearchError):
    """Raised when connection fails."""
    pass

class IndexError(ElasticsearchError):
    """Raised when index operation fails."""
    pass

class SearchError(ElasticsearchError):
    """Raised when search fails."""
    pass
```

## Configuration

```python
@dataclass
class ElasticsearchConfig:
    """Elasticsearch adapter configuration."""
    host: str = "localhost"
    port: int = 9200
    username: Optional[str] = None
    password: Optional[str] = None

    # Index settings
    event_index_pattern: str = "{type}-events-{date}"
    metric_index_pattern: str = "metrics-{date}"
    config_index: str = "platform-config"

    # Retention settings
    event_retention_days: int = 90
    metric_retention_days: int = 365

    # Performance settings
    bulk_size: int = 1000
    refresh_interval: str = "1s"
    number_of_shards: int = 1
    number_of_replicas: int = 0  # 0 for dev, 1+ for prod
```

## Testing Strategy

### Unit Tests

```python
import pytest

@pytest.fixture
def memory_store():
    return InMemoryEventStore()

async def test_store_and_retrieve(memory_store):
    """Test event storage and retrieval."""
    event = Event(
        id="test-1",
        timestamp=datetime.utcnow(),
        event_type=EventType.AGENT_COMPLETED,
        agent="test-agent",
        task_id="task-123",
        project="test-project",
        data={'duration': 10.5}
    )

    event_id = await memory_store.store_event(event)
    assert event_id == "test-1"

    retrieved = await memory_store.get_event(event_id)
    assert retrieved.agent == "test-agent"

async def test_search_filtering(memory_store):
    """Test event search with filters."""
    # Store multiple events
    for i in range(5):
        await memory_store.store_event(Event(
            id=f"event-{i}",
            timestamp=datetime.utcnow(),
            event_type=EventType.AGENT_COMPLETED,
            agent=f"agent-{i % 2}",
            task_id=f"task-{i}",
            project="test-project",
            data={}
        ))

    # Search for specific agent
    query = SearchQuery(
        query="",
        filters={'agent': 'agent-0'},
        size=100
    )

    results = await memory_store.search_events(query)
    assert len(results) == 3  # agents 0, 2, 4
```

## Summary

The Elasticsearch integration provides:
1. **Clean abstractions** through IEventStore and IConfigStore ports
2. **Production adapter** for real Elasticsearch operations
3. **Mock adapter** for in-memory testing
4. **Event storage** with automatic daily indexing
5. **Metrics tracking** with time-series support
6. **Configuration storage** replacing YAML files
7. **Search capabilities** with full-text and filtering
8. **Aggregations** for analytics
9. **Full testing** support without Elasticsearch dependency

This design enables the platform to use Elasticsearch for powerful search and analytics while maintaining flexibility to swap in alternative implementations (PostgreSQL, MongoDB) or run without Elasticsearch in test mode.
