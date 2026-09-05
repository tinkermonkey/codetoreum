# Shared Event Bus for Production Dogfooding

## Overview

Phase 3.1 wires a shared event bus (Elasticsearch) into the production bootstrap and trigger CLI to enable event distribution across processes. This resolves the MVP limitation where events published via trigger CLI never reached the application server.

## Architecture

### Event Store Selection

The system supports multiple event store implementations:

1. **InMemoryEventStore** (MVP default)
   - Single-process, no external dependencies
   - Suitable for development and unit testing
   - **Limitation**: Cannot be shared across process boundaries

2. **ElasticsearchEventStore** (Production recommended)
   - Distributed, cross-process event sharing
   - Persistent event log with indexing
   - **Requirement**: Elasticsearch 8.0+
   - **Configuration**: `ELASTICSEARCH_URL` environment variable

### Cross-Process Event Flow

```
┌─────────────────────────┐         ┌──────────────────────────┐
│   Trigger CLI Process   │         │  Application Server      │
│                         │         │                          │
│  1. CLIBootstrap        │         │  1. ProductionBootstrap  │
│     - Creates ES client │────────▶│     - Creates ES client  │
│     - Creates event_store        │     - Creates event_store │
│  2. Publishes event     │         │  2. Subscribes to events │
│     to ES               │         │     from ES              │
│                         │         │  3. Handles events via   │
│                         │         │     event bus            │
└─────────────────────────┘         └──────────────────────────┘
           │                                    ▲
           │                                    │
           └────▶ Elasticsearch Event Store ◀──┘
                  - Persistent event log
                  - Indexing & querying
```

## Configuration

### Environment Variables

```bash
# Elasticsearch connection (required for shared event bus)
export ELASTICSEARCH_URL="http://localhost:9200"

# GitHub credentials (required for ticket system)
export GITHUB_TOKEN="ghp_..."
export GITHUB_ORG="myorg"

# Optional: Claude API (for LLM provider)
export ANTHROPIC_API_KEY="sk-..."
```

### Default Adapter Selection

Production bootstrap automatically selects event store based on configuration:

```python
# File: src/codetoreum/infrastructure/bootstrap/production_bootstrap.py

adapter_config = AdapterSelectionConfig(
    board="github",
    ticket="github",
    llm="claude_code",
    version_control="github",
    container="docker",
    code_review="github",
    event_store="elasticsearch",  # ← Changed from "in_memory" for Phase 3.1
    # ... other adapters
)
```

Both production bootstrap and CLI bootstrap use the same Elasticsearch event store when configured with the same `ELASTICSEARCH_URL`.

## Implementation Details

### Event Store Factory

Helper functions for event store creation are provided in:
`src/codetoreum/adapters/secondary/event_store_factory.py`

```python
# Create Elasticsearch event store
from elasticsearch import AsyncElasticsearch
from codetoreum.adapters.secondary.event_store_factory import (
    create_elasticsearch_event_store,
    initialize_event_store,
)

es_client = AsyncElasticsearch(["http://localhost:9200"])
event_store = create_elasticsearch_event_store(es_client)
await initialize_event_store(event_store)
```

### Bootstrap Integration

**ProductionApplicationBootstrap**:
- Phase 1: Creates infrastructure (event bus)
- Phase 2: Adapter resolver creates event store based on `adapter_config.event_store`
- Factory automatically creates Elasticsearch client when `event_store="elasticsearch"`

**CLIBootstrap**:
- Creates shared event store using same Elasticsearch backend
- Enables CLI events to be published and retrieved by server
- Implements proper cleanup via `teardown()`

### Adapter Factory

Event store creation is handled by AdapterFactory:

```python
# File: src/codetoreum/infrastructure/adapters/factory.py

def create_event_store(self, adapter_name: str | None = None, **kwargs) -> IEventStore:
    """Create event store with automatic Elasticsearch client setup."""
    
    # For elasticsearch, creates client from ELASTICSEARCH_URL env var
    if resolved_name == "elasticsearch" and "es_client" not in kwargs:
        es_url = os.getenv("ELASTICSEARCH_URL", "http://localhost:9200")
        kwargs["es_client"] = AsyncElasticsearch([es_url])
    
    return self._event_store_registry.create_instance(resolved_name, **kwargs)
```

## Testing

### Integration Test

Cross-process event propagation is verified in:
`tests/integration/test_shared_event_bus.py`

Tests cover:
1. CLI and server share the same event store
2. Events published via CLI reach server via Elasticsearch
3. Event order and integrity maintained across boundaries
4. Stream isolation maintained across processes

**Run tests:**
```bash
# With Elasticsearch running on localhost:9200
pytest tests/integration/test_shared_event_bus.py -v

# Or with custom URL
ELASTICSEARCH_URL="http://my-es:9200" pytest tests/integration/test_shared_event_bus.py -v
```

## MVP Design Decision: InMemoryEventStore

### Why InMemoryEventStore was chosen for MVP

1. **Zero Dependencies**: No external services (Elasticsearch, Redis) required
2. **Fast Startup**: Perfect for development and testing
3. **Sufficient for Single Process**: Works for production bootstrap + application server on same process
4. **Test Isolation**: Each test gets fresh in-memory store

### Limitation Discovered in Phase E2

During dogfooding, discovered that **separate processes (CLI and server) cannot share InMemoryEventStore** because each process has its own memory space. Events published by CLI trigger never reached server event handlers.

### Migration Path

InMemoryEventStore → ElasticsearchEventStore:

1. **Set environment variable**:
   ```bash
   export ELASTICSEARCH_URL="http://localhost:9200"
   ```

2. **Start Elasticsearch**:
   ```bash
   docker run -d -p 9200:9200 \
     -e "discovery.type=single-node" \
     -e "xpack.security.enabled=false" \
     elasticsearch:8.17.0
   ```

3. **Bootstrap uses elasticsearch automatically**:
   - ProductionApplicationBootstrap detects `event_store="elasticsearch"` in AdapterSelectionConfig
   - CLIBootstrap also defaults to elasticsearch
   - Both create Elasticsearch clients from `ELASTICSEARCH_URL`

## Monitoring & Troubleshooting

### Event Store Health

Check Elasticsearch health:
```bash
curl http://localhost:9200/_cluster/health
```

### Event Index Status

View event indices:
```bash
curl http://localhost:9200/_cat/indices?v | grep events
```

### Debug Logging

Enable debug logging to trace event flow:
```python
import logging
logging.getLogger("codetoreum.infrastructure.bootstrap").setLevel(logging.DEBUG)
logging.getLogger("codetoreum.adapters.secondary.elasticsearch_event_store").setLevel(logging.DEBUG)
```

### Common Issues

**Issue**: "Failed to create Elasticsearch client"
- **Cause**: Elasticsearch not running or ELASTICSEARCH_URL incorrect
- **Fix**: Set ELASTICSEARCH_URL or start Elasticsearch container

**Issue**: Events not appearing in server
- **Cause**: CLI and server using different event stores
- **Fix**: Verify both use same ELASTICSEARCH_URL

**Issue**: Events visible but with delay
- **Cause**: Elasticsearch refresh interval (default 5s)
- **Fix**: Query with refresh flag or wait after publishing

## Future Improvements

1. **Redis Event Bus**: Add Redis pub/sub for real-time event streaming
2. **Event Compaction**: Implement snapshot-based event log compaction
3. **Multi-Region**: Support distributed Elasticsearch clusters
4. **Dead Letter Queue**: Comprehensive handling of failed event processing

## References

- **Event Store Contract**: `src/codetoreum/ports/output/event_store.py`
- **Elasticsearch Implementation**: `src/codetoreum/adapters/secondary/elasticsearch_event_store.py`
- **Production Bootstrap**: `src/codetoreum/infrastructure/bootstrap/production_bootstrap.py`
- **CLI Bootstrap**: `src/codetoreum/infrastructure/bootstrap/cli_bootstrap.py`
- **Event Store Factory**: `src/codetoreum/adapters/secondary/event_store_factory.py`
- **Design Doc**: `documentation/architecture/infrastructure/event-store.md` (if exists)
