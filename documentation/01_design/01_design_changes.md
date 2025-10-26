# Design Changes

## New capabilities

- The ability to manage environment variables at the project level.
  - Web UI to add/edit/delete environment variables for a project
  - Stored in Elasticsearch (`config-projects` index) with Redis caching

- The ability to mount commands and sub-agents into project agents.
  - Web UI to select which commands and sub-agents to mount into the project agent.

## Agent Containers

Update the agent design with the following interface changes.

### General Purpose Containerized Agents

- The general purpose containerized agents will NOT have access to:
  - git credentials or mounts
  - github credentials, app keys or mounts
  - ssh keys
  - docker socket or mounts

- The general purpose containerized agents will have access to:
  - internet access (for downloading dependencies, accessing APIs, etc.)
  - mounted project files (the files in the project repository), read/write or read-only based on configuration
  - environment variables defined at the project level
  - mounted commands and sub-agents defined at the project level
  - mounted mcp config and credentials for accessing MCP services (e.g., artifact storage, logging, etc.)
  - mounted request + context data (issues, pull requests, code snippets, etc.)

- Fundamentally change the way that the general purpose containerized agents receive context
  - Instead of passing in prompts combined with context, store the context in files that are mounted into the container
  - Pass in a reference to the context files in the prompt (e.g., "See the file /context/issue.txt for the issue description.")
  - This allows for much larger context to be passed to the agent without hitting token limits
  - This also allows for more complex context to be passed to the agent (e.g., multiple files, directories, etc.)

**Implications:**

- The Orchestrator will be responsible for managing git operations (clone, pull, push, etc.) and branch selection and will provide the necessary project files to the general purpose containerized agents, with the correct branch checked out.

- The Orchestrator will be responsible for collecting all context needed for the agent to perform its tasks, including issues, pull requests, code snippets, etc., and providing that context to the general purpose containerized agents.

## Persistence Architecture

### Elasticsearch + Redis Architecture

**Decision**: Use Elasticsearch as the primary persistence layer with Redis as a buffering and caching layer.

**Rationale**:

1. **Unified Observability Stack**
   - Elasticsearch provides a single platform for events, logs, and metrics
   - Native integration with Kibana for dashboards and visualization
   - Eliminates need for multiple storage systems

2. **Event Sourcing Requirements**
   - Full-text search across all domain events
   - Time-series data with index lifecycle management
   - Efficient querying by aggregate ID, event type, and timestamp
   - Point-in-time recovery via snapshots

3. **Configuration Management**
   - Full-text search across projects, workflows, and agents
   - Versioning with complete history
   - Easy discovery of configurations
   - No need for separate document database

4. **Performance Optimization**
   - **Redis Buffering**: High write throughput (10,000+ writes/sec)
   - **Redis Caching**: Sub-millisecond configuration reads
   - **Batch Persistence**: Background workers batch writes to Elasticsearch
   - **Horizontal Scaling**: Add workers for higher throughput

5. **Developer Experience**
   - Single query language (Elasticsearch DSL) for all data
   - Powerful aggregations for analytics
   - Time-travel debugging via event replay
   - Real-time log tailing during development

### Data Flow Pattern

```
Application
    ↓
Redis Streams (buffer) ─────→ Background Workers ─────→ Elasticsearch (persistence)
    ↓                                                          ↑
Real-time Event Bus                                   Queries & Search
```

**Write Path**:
1. Application writes to Redis Stream (< 1ms acknowledgment)
2. Background workers consume from Redis in batches
3. Workers bulk-insert to Elasticsearch (durability)
4. Events visible in Elasticsearch within ~5 seconds

**Read Path**:
1. Check Redis cache (hot data, < 1ms)
2. On cache miss, query Elasticsearch
3. Populate cache for future reads

### Storage Breakdown

| Data Type | Primary Storage | Buffer/Cache | Retention |
|-----------|----------------|--------------|-----------|
| Domain Events | Elasticsearch (`events-{YYYY.MM}`) | Redis Streams | 1 year (ILM) |
| Application Logs | Elasticsearch (`logs-{YYYY.MM.DD}`) | Redis Streams | 30 days (ILM) |
| Configurations | Elasticsearch (`config-*`) | Redis Hash/String | Indefinite |
| Metrics | Elasticsearch (`metrics-{YYYY.MM}`) | Redis aggregation | 90 days (ILM) |
| Config History | Elasticsearch (`config-history`) | None | Indefinite |

### Why Not PostgreSQL?

**PostgreSQL Drawbacks**:
- Requires separate search solution (full-text search limited)
- Complex time-series data management
- No native log aggregation features
- Additional operational overhead (backups, replication)
- Slower for event replay at scale

**Elasticsearch Advantages**:
- Purpose-built for time-series data
- Native full-text search
- Horizontal scaling built-in
- Index lifecycle management for retention
- Native log aggregation and analysis

### Consistency Model

**Eventual Consistency** (acceptable for our use case):
- Events acknowledged immediately upon Redis write
- Durable persistence within ~5 seconds
- Queries may not see most recent events
- Acceptable because:
  - Workflow execution is not latency-sensitive
  - Eventual consistency is fine for audit trail
  - UI can poll for updates if needed

**Strong Consistency** (when required):
- Query both Redis buffer and Elasticsearch
- Wait for Elasticsearch refresh (slower)
- Use only for critical operations (e.g., concurrency control)

### Disaster Recovery

**Redis Failure**:
- RDB + AOF persistence prevents data loss
- Workers resume from last acknowledged position
- No event loss if Redis data persists

**Elasticsearch Failure**:
- Events buffer in Redis until recovery
- Automated snapshots to S3 (daily)
- Point-in-time recovery via snapshot restore

**Worker Failure**:
- Consumer groups ensure reliable delivery
- Unacknowledged messages automatically retried
- No data loss

### Migration Path

**Phase 1**: Deploy Elasticsearch + Redis
- Set up Elasticsearch cluster
- Configure index templates and ILM policies
- Deploy Redis with persistence (RDB + AOF)

**Phase 2**: Migrate Configuration
- Import YAML configs to Elasticsearch indices
- Validate data integrity
- Enable Redis caching

**Phase 3**: Enable Event Sourcing
- Deploy background workers
- Route all events through Redis → Elasticsearch
- Validate event persistence

**Phase 4**: Cut Over
- Switch all queries to Elasticsearch
- Monitor performance and lag
- Optimize based on metrics
