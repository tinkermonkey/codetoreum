# Configuration Storage Adapters

This directory contains production-ready configuration storage implementations for Codetoreum Gen 2.

## Overview

The configuration storage system provides persistent, searchable configuration management with Redis caching for performance.

### Architecture

```
Application
    ↓
CachedConfigStore (Write-through cache)
    ↓
Redis Cache ← (cache miss) → Elasticsearch Storage
    ↓                              ↓
(cache hit)                    5 Indices:
    ↓                          - config-projects
Return cached config           - config-agents
                              - config-pipelines
                              - config-workflows
                              - config-history
```

## Components

### 1. ElasticsearchConfigStorage

**File**: `elasticsearch_config_storage.py`

Production storage adapter using Elasticsearch for persistent configuration storage.

**Features**:
- ✅ CRUD operations for all configuration types
- ✅ Full-text search across configurations
- ✅ Configuration versioning with audit trail
- ✅ Automatic index creation with custom analyzers
- ✅ Configurable sharding and replication
- ✅ Rollback capability via version history

**Usage**:
```python
from elasticsearch import AsyncElasticsearch
from codetoreum.adapters.secondary import ElasticsearchConfigStorage

es_client = AsyncElasticsearch(["http://localhost:9200"])
storage = ElasticsearchConfigStorage(
    es_client=es_client,
    shard_count=2,  # For production
    replica_count=1,  # For HA
)

await storage.initialize()

# Save config
await storage.save_project_config(project_config)

# Get config
project = await storage.get_project_config(project_id)

# Search
results = await storage.search_configs("api gateway", config_type="project")
```

### 2. RedisConfigCache

**File**: `../infrastructure/redis_config_cache.py`

Redis-backed cache for fast configuration reads.

**Features**:
- ✅ TTL-based cache expiration
- ✅ Pub/sub-based invalidation across instances
- ✅ Cache statistics tracking
- ✅ Write-through caching support
- ✅ Graceful degradation on failures

**Usage**:
```python
from redis import asyncio as aioredis
from codetoreum.infrastructure import RedisConfigCache

redis_client = aioredis.Redis(host="localhost", port=6379)
cache = RedisConfigCache(
    redis_client=redis_client,
    default_ttl=3600,  # 1 hour
)

await cache.initialize()

# Cache config
await cache.set_project_config(project_config)

# Get from cache
project = await cache.get_project_config(project_id)  # Returns None on miss

# Invalidate
await cache.invalidate_project(project_id)

# Get stats
stats = await cache.get_stats()
print(f"Hit rate: {stats['hit_rate']:.2%}")
```

### 3. CachedConfigStore

**File**: `cached_config_store.py`

Write-through cache decorator that combines Elasticsearch storage with Redis caching.

**Features**:
- ✅ Transparent caching (implements IConfigStore interface)
- ✅ Write-through: writes to storage, then cache
- ✅ Read-through: cache miss falls back to storage
- ✅ Automatic cache invalidation on updates/deletes
- ✅ Lists and searches bypass cache

**Usage**:
```python
from codetoreum.adapters.secondary import CachedConfigStore

cached_store = CachedConfigStore(
    storage=elasticsearch_storage,
    cache=redis_cache,
)

# Use like any IConfigStore
await cached_store.save_project_config(project)  # Writes to both
project = await cached_store.get_project_config(project_id)  # Cache-first
```

### 4. Factory Functions

**File**: `config_storage_factory.py`

Convenience functions for creating production-ready storage instances.

**Functions**:
- `create_elasticsearch_config_storage()`: Create ES storage
- `create_redis_config_cache()`: Create Redis cache
- `create_cached_config_store()`: Create combined ES + Redis setup
- `initialize_config_store()`: Initialize any store type
- `close_config_store()`: Clean up any store type

**Recommended Production Setup**:
```python
from elasticsearch import AsyncElasticsearch
from redis import asyncio as aioredis
from codetoreum.adapters.secondary import (
    create_cached_config_store,
    initialize_config_store,
    close_config_store,
)

# Create clients
es_client = AsyncElasticsearch([
    "http://es-node1:9200",
    "http://es-node2:9200",
    "http://es-node3:9200",
])
redis_client = aioredis.Redis(host="redis-primary", port=6379)

# Create cached store (production-ready)
config_store = create_cached_config_store(
    es_client=es_client,
    redis_client=redis_client,
    shard_count=3,      # Production sharding
    replica_count=2,    # High availability
    cache_ttl=3600,     # 1 hour cache
)

# Initialize
await initialize_config_store(config_store)

# Use it!
await config_store.save_project_config(project)
project = await config_store.get_project_config(project_id)

# Clean up
await close_config_store(config_store)
await es_client.close()
await redis_client.close()
```

## Elasticsearch Indices

### config-projects
Project configurations with tech stacks, pipelines, environment variables.

### config-agents
Agent configurations with models, timeouts, capabilities.

### config-pipelines
Pipeline configurations with stages and triggers.

### config-workflows
Workflow templates for reusable workflow definitions.

### config-history
Complete audit trail of all configuration changes with snapshots.

All indices use a custom `config_analyzer` for better search:
- Case-insensitive
- Accent-insensitive
- Word boundary detection

## Cache Key Pattern

```
config:project:{project_id}
config:project:name:{project_name}
config:agent:{project_id}:{agent_name}
config:pipeline:{project_id}:{pipeline_name}
config:workflow:{template_name}
```

## Caching Strategy

### What Gets Cached
- ✅ Individual project configs (by ID and name)
- ✅ Individual agent configs
- ✅ Individual pipeline configs
- ✅ Individual workflow templates

### What Does NOT Get Cached
- ❌ List operations (too complex to invalidate)
- ❌ Search results (query-dependent)
- ❌ Version history (historical data)
- ❌ Existence checks (avoid false negatives)

## Performance

### Typical Latencies
- **Cache hit**: 1-5ms
- **Cache miss + ES query**: 50-100ms
- **Write (ES + cache)**: 100-500ms
- **Search**: 50-200ms
- **Version history**: 100-300ms

### Expected Cache Hit Rate
- **Steady state**: 90%+ for frequently accessed configs
- **Cold start**: ~50% initially, warms up quickly
- **After updates**: Temporary dip, recovers quickly

## Configuration Versioning

Every configuration change creates a new version:

```python
# Save config multiple times
await storage.save_project_config(project)  # v1
project.tech_stacks["new_tool"] = "1.0"
await storage.save_project_config(project)  # v2
project.tech_stacks["new_tool"] = "2.0"
await storage.save_project_config(project)  # v3

# Get version history
versions = await storage.list_config_versions(project.id)
# Returns: [ConfigVersion(v3), ConfigVersion(v2), ConfigVersion(v1)]

# Get specific version
old_config = await storage.get_config_version(project.id, version=1)
# Returns: Full config snapshot from v1
```

## Search Capabilities

Full-text search across all configurations:

```python
# Single term search
results = await storage.search_configs("production")

# Multiple terms (AND logic)
results = await storage.search_configs("api gateway production")
# Returns configs containing ALL three terms

# Filtered search
results = await storage.search_configs(
    query="machine learning",
    config_type="project"  # Only search projects
)
```

## Testing

Comprehensive integration tests using testcontainers:

```bash
# Run all config storage tests
pytest tests/integration -v -k config

# Run Elasticsearch tests only
pytest tests/integration/adapters/secondary/test_elasticsearch_config_storage.py -v

# Run Redis cache tests only
pytest tests/integration/infrastructure/test_redis_config_cache_and_cached_store.py -v
```

## Production Deployment

### Prerequisites
- Elasticsearch 8.x cluster (3+ nodes recommended)
- Redis 7.x (standalone or cluster)
- Docker (for testcontainers in tests)

### Elasticsearch Setup
```bash
# Minimum cluster configuration
- 3 nodes
- 2-5 shards per index
- 1-2 replicas for HA
- ILM policy for config-history rotation
- Snapshot policy for backups
```

### Redis Setup
```bash
# Standalone with replication
- Primary + 1-2 replicas
- AOF + RDB persistence
- Memory limit: 2-4GB
- Eviction policy: allkeys-lru
```

### Monitoring
- Elasticsearch cluster health
- Elasticsearch query latency
- Redis memory usage
- Redis cache hit rate (target: >90%)
- Configuration read/write latencies

## Migration from InMemoryConfigStore

The new storage is fully compatible with the existing `IConfigStore` interface:

```python
# Before (in-memory)
from codetoreum.adapters.testing import InMemoryConfigStore
config_store = InMemoryConfigStore()

# After (production)
from codetoreum.adapters.secondary import create_cached_config_store
config_store = create_cached_config_store(es_client, redis_client)
await initialize_config_store(config_store)

# All existing code works unchanged!
```

## Troubleshooting

### High Cache Miss Rate
- Check Redis connectivity
- Verify cache TTL is appropriate
- Check for frequent invalidations
- Monitor cache memory usage

### Slow Elasticsearch Queries
- Check cluster health
- Review shard allocation
- Verify index templates are applied
- Check query complexity

### Configuration Not Found
- Check Elasticsearch refresh interval
- Verify index exists
- Check document was successfully indexed
- Review version numbers

## References

- **Implementation Plan**: `/workspace/documentation/01_design/03_implementation_plan.md` (Phase 7)
- **Summary**: `/workspace/PHASE_7_PART_1_SUMMARY.md`
- **Port Interface**: `/workspace/src/codetoreum/ports/output/config_store.py`
- **Tests**: `/workspace/tests/integration/` (adapters/secondary and infrastructure)

## Next Steps

Phase 7 - Part 2 will add:
- Configuration templates with search
- Enhanced ConfigurationService integration
- Configuration web UI
- YAML migration tool

See `/workspace/PHASE_7_PART_1_SUMMARY.md` for complete details.
