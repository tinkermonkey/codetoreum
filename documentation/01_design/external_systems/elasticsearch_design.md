# Elasticsearch External System - Detailed Design

## Overview

Elasticsearch serves as the **optional persistence layer** for the Codetoreum platform, providing distributed search, analytics, and storage capabilities. This external system is designed for use in production environments requiring durable event storage and full-text search capabilities.

**Current Implementation Status**:
- **Event Sourcing Adapter**: Implemented (`ElasticsearchEventStore`) but not yet integrated into production
- **Configuration Storage**: Actively used (`ElasticsearchConfigStorage`) with Redis caching
- **Production Readiness**: Design complete and tested; deployment requires configuration

**Planned Functions**:
- **Event Sourcing**: Persistent storage of all domain events (not yet in production)
- **Logging**: Application and execution logs (design only)
- **Configuration**: Project, workflow, and agent configurations (configuration only, not events)
- **Metrics**: Performance and business metrics (design only)
- **Search**: Full-text search across all data (design only)

**Architecture Pattern**: Elasticsearch is accessed via Redis buffering for high-throughput writes:
```
Application → Redis Streams (buffer) → Background Workers → Elasticsearch (persistence)
```

**Note**: Current production deployments use `InMemoryEventStore` for event persistence. To enable Elasticsearch-backed persistence, configure the adapter factory to register `ElasticsearchEventStore` and wire up the `RedisEventBuffer` with background worker threads.

## System Purpose

**Planned Primary Functions**:
1. **Event Sourcing Storage**: Complete audit trail of all domain events (when enabled)
2. **Log Aggregation**: Centralized logging from all services and agent executions (design phase)
3. **Configuration Management**: Database replacement for YAML configurations (partially implemented)
4. **Metrics Storage**: Time-series performance and business metrics (design phase)
5. **Full-Text Search**: Search across events, logs, configurations (design phase)
6. **Analytics**: Pattern detection, aggregations, anomaly analysis (design phase)
7. **Debugging**: Historical replay and troubleshooting (when event storage enabled)

**Current Implementation**:
- ✅ Configuration storage with versioning and history tracking
- ✅ Redis caching layer for performance (CachedConfigStore)
- ⏳ Event storage adapter implemented but not active (see "Migration Path" section)
- ❌ Logging aggregation (design only)
- ❌ Metrics storage (design only)
- ❌ Full-text search capabilities (design only)

## Migration Path: From InMemory to Elasticsearch

### Current State (v1.0)
The system currently uses `InMemoryEventStore` for all event persistence:
- All events stored in memory
- No persistence across restarts
- Suitable for development, testing, and simulation
- Suitable for stateless deployments with external event log coordination

### Production Deployment Path
To enable Elasticsearch-backed event persistence:

1. **Register ElasticsearchEventStore in adapter factory** (`infrastructure/adapters/factory.py`):
   ```python
   self._event_store_registry.register(
       name="elasticsearch",
       adapter_type=ElasticsearchEventStore,
       description="Elasticsearch-based event store with Redis buffering",
       version="1.0.0",
       tags=["production"],
       set_as_default=True  # Enable for production
   )
   ```

2. **Configure Elasticsearch connection** in environment:
   ```
   ELASTICSEARCH_HOSTS=elasticsearch:9200
   ELASTICSEARCH_INDEX_PREFIX=events
   ```

3. **Start Redis event buffer workers**:
   ```python
   # In application startup
   buffer = RedisEventBuffer(redis_client)
   worker = EventPersistenceWorker(
       redis_client=redis_client,
       elasticsearch_store=es_store,
       worker_id="worker-1"
   )
   await worker.process_events_loop()  # Run in background
   ```

4. **Verify indices and ILM policies** exist in Elasticsearch (see Index Architecture section)

### Benefits of Migration
- ✅ Persistent event log survives application restarts
- ✅ Event replay for debugging and audit
- ✅ Full-text search across events
- ✅ ILM-managed data retention
- ✅ High-throughput writes with Redis buffering
- ✅ Horizontal scaling with multiple worker threads

## Data Flow Architecture

### Write Path
```
Application
    ↓
Redis Streams (buffering)
    ↓
Consumer Groups (background workers)
    ↓
Batch Processing
    ↓
Elasticsearch Bulk API
    ↓
Persistent Storage
```

### Read Path
```
Application Query
    ↓
Redis Cache (for hot data)
    ├─ Cache Hit → Return
    └─ Cache Miss ↓
Elasticsearch Query
    ↓
Update Redis Cache
    ↓
Return Results
```

## Index Architecture

### 1. Event Indices

**Index Pattern**: `events-{YYYY.MM}`

**Purpose**: Event sourcing - complete history of all domain events

**Mapping**:
```json
{
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
      "data": {"type": "object", "enabled": true},
      "metadata": {
        "properties": {
          "trace_id": {"type": "keyword"},
          "span_id": {"type": "keyword"},
          "service": {"type": "keyword"}
        }
      }
    }
  },
  "settings": {
    "number_of_shards": 2,
    "number_of_replicas": 1,
    "refresh_interval": "5s",
    "index.lifecycle.name": "events-policy"
  }
}
```

**ILM Policy**:
```json
{
  "policy": {
    "phases": {
      "hot": {
        "actions": {
          "rollover": {
            "max_age": "30d",
            "max_size": "50gb"
          }
        }
      },
      "warm": {
        "min_age": "30d",
        "actions": {
          "shrink": {"number_of_shards": 1},
          "forcemerge": {"max_num_segments": 1}
        }
      },
      "cold": {
        "min_age": "90d",
        "actions": {
          "freeze": {}
        }
      },
      "delete": {
        "min_age": "365d",
        "actions": {
          "delete": {}
        }
      }
    }
  }
}
```

### 2. Log Indices

**Index Pattern**: `logs-{YYYY.MM.DD}`

**Purpose**: Application logs, execution logs, system logs

**Mapping**:
```json
{
  "mappings": {
    "properties": {
      "timestamp": {"type": "date"},
      "level": {"type": "keyword"},
      "logger": {"type": "keyword"},
      "message": {"type": "text"},
      "service": {"type": "keyword"},
      "environment": {"type": "keyword"},
      "trace_id": {"type": "keyword"},
      "span_id": {"type": "keyword"},
      "execution_id": {"type": "keyword"},
      "work_item_id": {"type": "keyword"},
      "agent_name": {"type": "keyword"},
      "project": {"type": "keyword"},
      "error": {
        "properties": {
          "type": {"type": "keyword"},
          "message": {"type": "text"},
          "stack_trace": {"type": "text"}
        }
      },
      "context": {"type": "object", "enabled": true}
    }
  },
  "settings": {
    "number_of_shards": 1,
    "number_of_replicas": 1,
    "refresh_interval": "5s",
    "index.lifecycle.name": "logs-policy"
  }
}
```

**ILM Policy**:
```json
{
  "policy": {
    "phases": {
      "hot": {
        "actions": {
          "rollover": {
            "max_age": "1d",
            "max_size": "10gb"
          }
        }
      },
      "delete": {
        "min_age": "30d",
        "actions": {
          "delete": {}
        }
      }
    }
  }
}
```

### 3. Configuration Indices

**Index Pattern**: `config-{type}` (e.g., `config-projects`, `config-workflows`)

**Purpose**: Replaces YAML configuration files with searchable, versioned storage

**Projects Index**: `config-projects`
```json
{
  "mappings": {
    "properties": {
      "project_id": {"type": "keyword"},
      "name": {"type": "text", "fields": {"keyword": {"type": "keyword"}}},
      "description": {"type": "text"},
      "github_org": {"type": "keyword"},
      "github_repo": {"type": "keyword"},
      "tech_stack": {"type": "keyword"},
      "environment_variables": {"type": "object", "enabled": true},
      "mounted_commands": {"type": "object", "enabled": true},
      "version": {"type": "integer"},
      "created_at": {"type": "date"},
      "updated_at": {"type": "date"},
      "created_by": {"type": "keyword"},
      "is_active": {"type": "boolean"}
    }
  },
  "settings": {
    "number_of_shards": 1,
    "number_of_replicas": 1,
    "refresh_interval": "1s"
  }
}
```

**Workflows Index**: `config-workflows`
```json
{
  "mappings": {
    "properties": {
      "workflow_id": {"type": "keyword"},
      "name": {"type": "text", "fields": {"keyword": {"type": "keyword"}}},
      "description": {"type": "text"},
      "project_id": {"type": "keyword"},
      "stages": {
        "type": "nested",
        "properties": {
          "stage_id": {"type": "keyword"},
          "name": {"type": "keyword"},
          "agent_type": {"type": "keyword"},
          "entry_conditions": {"type": "object"},
          "config": {"type": "object"}
        }
      },
      "version": {"type": "integer"},
      "created_at": {"type": "date"},
      "updated_at": {"type": "date"},
      "is_active": {"type": "boolean"}
    }
  }
}
```

**Agents Index**: `config-agents`
```json
{
  "mappings": {
    "properties": {
      "agent_id": {"type": "keyword"},
      "name": {"type": "text", "fields": {"keyword": {"type": "keyword"}}},
      "agent_type": {"type": "keyword"},
      "prompt_template": {"type": "text"},
      "capabilities": {"type": "keyword"},
      "constraints": {"type": "object"},
      "version": {"type": "integer"},
      "created_at": {"type": "date"},
      "updated_at": {"type": "date"},
      "is_active": {"type": "boolean"}
    }
  }
}
```

**Configuration History Index**: `config-history`
```json
{
  "mappings": {
    "properties": {
      "change_id": {"type": "keyword"},
      "config_type": {"type": "keyword"},
      "config_id": {"type": "keyword"},
      "action": {"type": "keyword"},
      "previous_version": {"type": "integer"},
      "new_version": {"type": "integer"},
      "changes": {"type": "object", "enabled": true},
      "changed_by": {"type": "keyword"},
      "changed_at": {"type": "date"},
      "reason": {"type": "text"}
    }
  }
}
```

### 4. Metrics Indices

**Index Pattern**: `metrics-{YYYY.MM}`

**Purpose**: Performance metrics, business metrics, system health

**Mapping**:
```json
{
  "mappings": {
    "properties": {
      "metric_id": {"type": "keyword"},
      "timestamp": {"type": "date"},
      "metric_name": {"type": "keyword"},
      "metric_type": {"type": "keyword"},
      "value": {"type": "double"},
      "unit": {"type": "keyword"},
      "tags": {
        "properties": {
          "project": {"type": "keyword"},
          "agent": {"type": "keyword"},
          "execution_id": {"type": "keyword"},
          "environment": {"type": "keyword"}
        }
      },
      "dimensions": {"type": "object", "enabled": true}
    }
  },
  "settings": {
    "index.lifecycle.name": "metrics-policy"
  }
}
```

## Port Interface Design

### IEventStore Interface

```python
from abc import ABC, abstractmethod
from typing import List, Optional, AsyncIterator, Dict, Any
from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

@dataclass
class DomainEvent:
    """Domain event for event sourcing."""
    event_id: str
    aggregate_id: str
    aggregate_type: str
    event_type: str
    event_version: int
    timestamp: datetime
    stream_version: int
    data: Dict[str, Any]
    metadata: Dict[str, Any]
    correlation_id: Optional[str] = None
    causation_id: Optional[str] = None

class IEventStore(ABC):
    """
    Port interface for event sourcing persistence.

    Production: ElasticsearchEventStore with RedisEventBuffer
    Testing: InMemoryEventStore
    """

    @abstractmethod
    async def append(self,
                     stream_id: str,
                     events: List[DomainEvent],
                     expected_version: Optional[int] = None) -> None:
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
        pass

    @abstractmethod
    async def get_events(self,
                        stream_id: str,
                        from_version: int = 0,
                        to_version: Optional[int] = None) -> List[DomainEvent]:
        """Get events from a stream."""
        pass

    @abstractmethod
    async def get_events_since(self,
                              since: datetime,
                              stream_id: Optional[str] = None,
                              event_types: Optional[List[str]] = None) -> List[DomainEvent]:
        """Get events since a timestamp, optionally filtered by type."""
        pass

    @abstractmethod
    async def stream_events(self,
                           stream_id: Optional[str] = None,
                           from_version: int = 0) -> AsyncIterator[DomainEvent]:
        """Stream events in real-time."""
        pass

    @abstractmethod
    async def get_stream_version(self, stream_id: str) -> int:
        """Get current version of a stream."""
        pass

    @abstractmethod
    async def search_events(self,
                           query: str,
                           filters: Optional[Dict[str, Any]] = None,
                           start_time: Optional[datetime] = None,
                           end_time: Optional[datetime] = None,
                           limit: int = 100) -> List[DomainEvent]:
        """Search events with full-text query and filters."""
        pass
```

### IConfigStore Interface

```python
@dataclass
class ProjectConfig:
    """Project configuration."""
    project_id: str
    name: str
    description: str
    github_org: str
    github_repo: str
    tech_stack: str
    environment_variables: Dict[str, str]
    mounted_commands: Dict[str, Any]
    version: int
    created_at: datetime
    updated_at: datetime
    created_by: str
    is_active: bool = True

@dataclass
class WorkflowConfig:
    """Workflow configuration."""
    workflow_id: str
    name: str
    description: str
    project_id: str
    stages: List[Dict[str, Any]]
    version: int
    created_at: datetime
    updated_at: datetime
    is_active: bool = True

@dataclass
class AgentConfig:
    """Agent configuration."""
    agent_id: str
    name: str
    agent_type: str
    prompt_template: str
    capabilities: List[str]
    constraints: Dict[str, Any]
    version: int
    created_at: datetime
    updated_at: datetime
    is_active: bool = True

class IConfigStore(ABC):
    """
    Port interface for configuration storage.

    Replaces YAML files with Elasticsearch-backed storage.

    Production: ElasticsearchConfigStore with RedisConfigCache
    Testing: InMemoryConfigStore
    """

    @abstractmethod
    async def get_project(self, project_id: str) -> Optional[ProjectConfig]:
        """Get project configuration."""
        pass

    @abstractmethod
    async def save_project(self, config: ProjectConfig) -> str:
        """Save project configuration (creates new version)."""
        pass

    @abstractmethod
    async def list_projects(self, active_only: bool = True) -> List[ProjectConfig]:
        """List all projects."""
        pass

    @abstractmethod
    async def get_workflow(self, workflow_id: str) -> Optional[WorkflowConfig]:
        """Get workflow configuration."""
        pass

    @abstractmethod
    async def save_workflow(self, config: WorkflowConfig) -> str:
        """Save workflow configuration (creates new version)."""
        pass

    @abstractmethod
    async def list_workflows(self, project_id: Optional[str] = None) -> List[WorkflowConfig]:
        """List workflows, optionally filtered by project."""
        pass

    @abstractmethod
    async def get_agent(self, agent_id: str) -> Optional[AgentConfig]:
        """Get agent configuration."""
        pass

    @abstractmethod
    async def save_agent(self, config: AgentConfig) -> str:
        """Save agent configuration (creates new version)."""
        pass

    @abstractmethod
    async def search_configs(self,
                            query: str,
                            config_type: Optional[str] = None) -> List[Dict[str, Any]]:
        """Full-text search across configurations."""
        pass

    @abstractmethod
    async def get_config_history(self,
                                config_id: str,
                                limit: int = 10) -> List[Dict[str, Any]]:
        """Get configuration change history."""
        pass

    @abstractmethod
    async def rollback_config(self,
                             config_id: str,
                             to_version: int) -> None:
        """Rollback configuration to a previous version."""
        pass
```

### ILogStore Interface

```python
@dataclass
class LogEntry:
    """Structured log entry."""
    timestamp: datetime
    level: str
    logger: str
    message: str
    service: str
    environment: str
    trace_id: Optional[str] = None
    span_id: Optional[str] = None
    execution_id: Optional[str] = None
    work_item_id: Optional[str] = None
    agent_name: Optional[str] = None
    project: Optional[str] = None
    error: Optional[Dict[str, Any]] = None
    context: Optional[Dict[str, Any]] = None

class ILogStore(ABC):
    """
    Port interface for log storage.

    Production: ElasticsearchLogStore with RedisLogBuffer
    Testing: InMemoryLogStore
    """

    @abstractmethod
    async def write_log(self, entry: LogEntry) -> None:
        """Write a single log entry."""
        pass

    @abstractmethod
    async def write_logs_bulk(self, entries: List[LogEntry]) -> None:
        """Write multiple log entries (batch operation)."""
        pass

    @abstractmethod
    async def query_logs(self,
                        query: str,
                        filters: Optional[Dict[str, Any]] = None,
                        start_time: Optional[datetime] = None,
                        end_time: Optional[datetime] = None,
                        limit: int = 100) -> List[LogEntry]:
        """Query logs with full-text search."""
        pass

    @abstractmethod
    async def get_execution_logs(self,
                                execution_id: str,
                                level: Optional[str] = None) -> List[LogEntry]:
        """Get all logs for a specific execution."""
        pass

    @abstractmethod
    async def stream_logs(self,
                         filters: Optional[Dict[str, Any]] = None) -> AsyncIterator[LogEntry]:
        """Stream logs in real-time."""
        pass
```

## Production Adapters

### ElasticsearchEventStore

```python
from elasticsearch import AsyncElasticsearch
from datetime import datetime
import json

class ElasticsearchEventStore(IEventStore):
    """
    Production event store using Elasticsearch.

    Events are written to Redis first, then persisted to Elasticsearch
    by background workers for durability and high throughput.
    """

    def __init__(
        self,
        es_client: AsyncElasticsearch,
        index_prefix: str = "events"
    ):
        self.client = es_client
        self.index_prefix = index_prefix

    async def append(self,
                     stream_id: str,
                     events: List[DomainEvent],
                     expected_version: Optional[int] = None) -> None:
        """Append events to stream with optimistic concurrency control."""

        # Check current version if expected version provided
        if expected_version is not None:
            current_version = await self.get_stream_version(stream_id)
            if current_version != expected_version:
                raise ConcurrencyConflictError(
                    f"Expected version {expected_version}, got {current_version}"
                )

        # Prepare bulk request
        bulk_body = []
        for event in events:
            index_name = self._get_index_name(event.timestamp)

            bulk_body.append({
                "index": {
                    "_index": index_name,
                    "_id": event.event_id
                }
            })

            bulk_body.append({
                "event_id": event.event_id,
                "aggregate_id": event.aggregate_id,
                "aggregate_type": event.aggregate_type,
                "event_type": event.event_type,
                "event_version": event.event_version,
                "timestamp": event.timestamp.isoformat(),
                "stream_version": event.stream_version,
                "correlation_id": event.correlation_id,
                "causation_id": event.causation_id,
                "data": event.data,
                "metadata": event.metadata
            })

        # Execute bulk insert
        await self.client.bulk(body=bulk_body, refresh=False)

    async def get_events(self,
                        stream_id: str,
                        from_version: int = 0,
                        to_version: Optional[int] = None) -> List[DomainEvent]:
        """Get events from a stream."""

        query = {
            "bool": {
                "must": [
                    {"term": {"aggregate_id": stream_id}},
                    {"range": {"stream_version": {"gte": from_version}}}
                ]
            }
        }

        if to_version is not None:
            query["bool"]["must"].append({
                "range": {"stream_version": {"lte": to_version}}
            })

        response = await self.client.search(
            index=f"{self.index_prefix}-*",
            query=query,
            sort=[{"stream_version": "asc"}],
            size=10000
        )

        return [self._to_domain_event(hit["_source"]) for hit in response["hits"]["hits"]]

    async def search_events(self,
                           query: str,
                           filters: Optional[Dict[str, Any]] = None,
                           start_time: Optional[datetime] = None,
                           end_time: Optional[datetime] = None,
                           limit: int = 100) -> List[DomainEvent]:
        """Search events with full-text query."""

        es_query = {"bool": {"must": []}}

        if query:
            es_query["bool"]["must"].append({
                "query_string": {"query": query}
            })

        if filters:
            for field, value in filters.items():
                es_query["bool"]["must"].append({
                    "term": {field: value}
                })

        if start_time or end_time:
            time_range = {}
            if start_time:
                time_range["gte"] = start_time.isoformat()
            if end_time:
                time_range["lte"] = end_time.isoformat()
            es_query["bool"]["must"].append({
                "range": {"timestamp": time_range}
            })

        response = await self.client.search(
            index=f"{self.index_prefix}-*",
            query=es_query,
            size=limit,
            sort=[{"timestamp": "desc"}]
        )

        return [self._to_domain_event(hit["_source"]) for hit in response["hits"]["hits"]]

    def _get_index_name(self, timestamp: datetime) -> str:
        """Generate index name with monthly rollover."""
        return f"{self.index_prefix}-{timestamp.strftime('%Y.%m')}"

    def _to_domain_event(self, doc: Dict[str, Any]) -> DomainEvent:
        """Convert Elasticsearch document to DomainEvent."""
        return DomainEvent(
            event_id=doc["event_id"],
            aggregate_id=doc["aggregate_id"],
            aggregate_type=doc["aggregate_type"],
            event_type=doc["event_type"],
            event_version=doc["event_version"],
            timestamp=datetime.fromisoformat(doc["timestamp"]),
            stream_version=doc["stream_version"],
            data=doc["data"],
            metadata=doc["metadata"],
            correlation_id=doc.get("correlation_id"),
            causation_id=doc.get("causation_id")
        )
```

### ElasticsearchConfigStore

```python
class ElasticsearchConfigStore(IConfigStore):
    """
    Production config store using Elasticsearch.

    Provides versioning, history tracking, and full-text search.
    """

    def __init__(self, es_client: AsyncElasticsearch):
        self.client = es_client

    async def save_project(self, config: ProjectConfig) -> str:
        """Save project configuration with versioning."""

        # Get current version
        current = await self.get_project(config.project_id)
        if current:
            config.version = current.version + 1
        else:
            config.version = 1

        config.updated_at = datetime.utcnow()

        # Store new version
        doc_id = f"{config.project_id}-v{config.version}"
        await self.client.index(
            index="config-projects",
            id=doc_id,
            document={
                "project_id": config.project_id,
                "name": config.name,
                "description": config.description,
                "github_org": config.github_org,
                "github_repo": config.github_repo,
                "tech_stack": config.tech_stack,
                "environment_variables": config.environment_variables,
                "mounted_commands": config.mounted_commands,
                "version": config.version,
                "created_at": config.created_at.isoformat(),
                "updated_at": config.updated_at.isoformat(),
                "created_by": config.created_by,
                "is_active": config.is_active
            }
        )

        # Record change in history
        await self._record_config_change(
            config_type="project",
            config_id=config.project_id,
            new_version=config.version,
            changed_by=config.created_by
        )

        return doc_id

    async def search_configs(self,
                            query: str,
                            config_type: Optional[str] = None) -> List[Dict[str, Any]]:
        """Full-text search across configurations."""

        indices = []
        if config_type:
            indices = [f"config-{config_type}"]
        else:
            indices = ["config-*"]

        es_query = {
            "bool": {
                "must": [
                    {"query_string": {"query": query}},
                    {"term": {"is_active": True}}
                ]
            }
        }

        response = await self.client.search(
            index=indices,
            query=es_query,
            size=100
        )

        return [hit["_source"] for hit in response["hits"]["hits"]]

    async def _record_config_change(self,
                                   config_type: str,
                                   config_id: str,
                                   new_version: int,
                                   changed_by: str) -> None:
        """Record configuration change in history index."""
        await self.client.index(
            index="config-history",
            document={
                "config_type": config_type,
                "config_id": config_id,
                "new_version": new_version,
                "changed_by": changed_by,
                "changed_at": datetime.utcnow().isoformat()
            }
        )
```

## Redis Buffering Architecture

All writes to Elasticsearch go through Redis first:

```python
class RedisEventBuffer:
    """
    Buffers events in Redis Streams before Elasticsearch persistence.

    Provides:
    - High-throughput writes
    - Reliable delivery via consumer groups
    - Backpressure handling
    """

    def __init__(self, redis_client):
        self.redis = redis_client
        self.stream_name = "events:buffer"

    async def buffer_event(self, event: DomainEvent) -> None:
        """Write event to Redis Stream."""
        await self.redis.xadd(
            self.stream_name,
            {
                "event_id": event.event_id,
                "aggregate_id": event.aggregate_id,
                "payload": json.dumps({
                    "event_type": event.event_type,
                    "data": event.data,
                    "metadata": event.metadata
                })
            }
        )

class EventPersistenceWorker:
    """
    Background worker that reads from Redis and persists to Elasticsearch.

    Uses consumer groups for reliable delivery and parallel processing.
    """

    async def process_events(self):
        """Read events from Redis and persist to Elasticsearch."""
        while True:
            # Read batch from Redis Stream
            messages = await self.redis.xreadgroup(
                groupname="elasticsearch-writers",
                consumername=self.worker_id,
                streams={self.stream_name: ">"},
                count=100,
                block=1000
            )

            if not messages:
                continue

            # Batch write to Elasticsearch
            events = [self._parse_event(msg) for msg in messages]
            await self.es_store.append_batch(events)

            # Acknowledge processing
            await self.redis.xack(
                self.stream_name,
                "elasticsearch-writers",
                *[msg["id"] for msg in messages]
            )
```

## Backup and Recovery

### Snapshot Configuration

```python
# Create snapshot repository
PUT /_snapshot/backup_repo
{
  "type": "s3",
  "settings": {
    "bucket": "codetoreum-backups",
    "region": "us-east-1",
    "base_path": "elasticsearch-snapshots"
  }
}

# Configure automated snapshots
PUT /_slm/policy/daily-snapshots
{
  "schedule": "0 0 * * *",
  "name": "<daily-snap-{now/d}>",
  "repository": "backup_repo",
  "config": {
    "indices": ["events-*", "config-*", "logs-*"],
    "include_global_state": false
  },
  "retention": {
    "expire_after": "30d",
    "min_count": 7,
    "max_count": 30
  }
}
```

### Point-in-Time Recovery

```python
async def restore_to_point_in_time(self, timestamp: datetime):
    """Restore system to a specific point in time."""
    # 1. Find snapshot closest to timestamp
    # 2. Restore snapshot
    # 3. Replay events from snapshot time to target time
    pass
```

## Summary

Elasticsearch serves as the **primary persistence layer** for Codetoreum, providing:

1. **Event Sourcing**: Complete audit trail with event replay capability
2. **Logging**: Centralized logs from all services and executions
3. **Configuration**: Versioned, searchable configuration management
4. **Metrics**: Time-series performance and business metrics
5. **Search**: Full-text search across all data types
6. **Analytics**: Aggregations, pattern detection, anomaly analysis
7. **Durability**: Snapshots, replication, and disaster recovery

**Architecture Benefits**:
- Redis buffering provides high write throughput
- Elasticsearch provides powerful search and analytics
- Index lifecycle management handles data retention
- Full-text search enables configuration discovery
- Event sourcing enables time-travel debugging
- Versioning enables safe configuration rollback
