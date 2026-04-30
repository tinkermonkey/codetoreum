---
template: adapter-template.md
applies_to: "documentation/architecture/adapters/production/**/*adapter*.md"
---

# Infrastructure Adapters

## Purpose

Infrastructure adapters provide cross-cutting services required by the application: event persistence, configuration storage, metrics collection, message distribution, CI/CD integration, repair cycle management, and error analysis.

Unlike core system adapters (GitHub, Docker, Claude) that implement primary business domain ports, infrastructure adapters implement secondary ports for operational concerns. They enable observability, event sourcing, resilience, and advanced features like intelligent repair cycles.

## Overview

| Adapter | Port Interface | External System | Purpose |
|---|---|---|---|
| **ElasticsearchEventStore** | IEventStore | Elasticsearch | Event persistence for audit trail and replay |
| **ElasticsearchConfigStorage** | IConfigStore | Elasticsearch | Configuration storage with versioning |
| **PrometheusMetricsAdapter** | IMetrics | Prometheus | Metrics collection and time-series storage |
| **RedisPubSubAdapter** | IMessageBroker, IEventEmitter | Redis | Pub/sub event distribution and messaging |
| **GitHubCIPipelineAdapter** | ICIPipelineService | GitHub Actions | CI/CD pipeline status tracking |
| **ProductionRepairCycleAdapter** | IRepairCycle | Codetoreum agents | Intelligent repair cycles for failing workflows |
| **ProductionEnvironmentRepairAdapter** | IEnvironmentRepairService | External tools | Environment repair for dependency issues |
| **LLMSystemicAnalysisAdapter** | ISystemicAnalysisService | Claude Code | LLM-based failure analysis |
| **BranchResolutionAdapter** | IBranchResolutionService | Git + GitHub | Intelligent branch conflict resolution |
| **DockerContainerRecoveryAdapter** | IAgentContainerRecoveryService | Docker | Container failure recovery and restart |
| **GitHubDiscussionAdapter** | IDiscussionAdapter | GitHub Discussions | Discussion and comment management |

## Detailed Specifications

### Event Store Adapters

#### ElasticsearchEventStore (IEventStore)

**Purpose**: Persist domain events for complete audit trail, event replay, and event sourcing.

**Implementation**:
- Stores immutable domain events as JSON documents
- Index per event type for efficient queries
- Snapshot support for large event streams
- TTL-based retention policies
- Full-text search on event data

**Configuration**:
```python
elasticsearch_hosts: list[str] = ["http://localhost:9200"]
index_prefix: str = "codetoreum-events"
event_retention_days: int = 365  # 1 year default
snapshot_interval: int = 1000     # Snapshot every 1000 events
bulk_flush_size: int = 500        # Batch writes for performance
```

**Error Handling**:
- Connection failures: Automatic retry with exponential backoff
- Index creation failures: Create with default mapping if not exists
- Bulk write failures: Log and continue (partial failures tracked)
- Query failures: Fallback to local in-memory cache

**Testing**:
- Testcontainers for real Elasticsearch (integration tests)
- Mock Elasticsearch responses (unit tests)
- Event replay verification
- Query performance benchmarks

---

#### InMemoryEventStore (Simulation Alternative)

Deterministic in-memory event storage used in simulation tests. Provides same IEventStore interface but without external dependencies.

### Configuration Storage Adapters

#### ElasticsearchConfigStorage (IConfigStore)

**Purpose**: Store application configuration (workflow definitions, agent configs, project settings) with versioning and rollback support.

**Implementation**:
- Document-based storage with version history
- Supports branching for configuration experiments
- Audit trail of configuration changes
- Active/draft/archived status
- Partial updates without full document rewrite

**Configuration**:
```python
elasticsearch_hosts: list[str] = ["http://localhost:9200"]
index_prefix: str = "codetoreum-config"
max_versions_per_config: int = 100  # Keep last 100 versions
default_ttl_days: int = 0            # No TTL (keep indefinitely)
```

**Cache Layer**:
```python
class CachedConfigStore(IConfigStore):
    """Caches configuration in memory to avoid repeated ES queries."""
    cache_ttl_seconds: int = 300      # 5 minute cache
    cache_max_size: int = 1000        # Max 1000 entries
```

---

### Metrics Collection

#### PrometheusMetricsAdapter (IMetrics)

**Purpose**: Collect and expose operational metrics (timing, counters, gauges, histograms) for monitoring.

**Metrics Types**:
- **Counters**: Total events, errors, operations
- **Gauges**: Active executions, queue length, memory usage
- **Histograms**: Latency distributions, payload sizes
- **Timers**: Operation durations

**Example Metrics**:
```
codetoreum_workflow_executions_total{status="success"}
codetoreum_agent_execution_duration_seconds{agent_type="code_analyst"}
codetoreum_event_processing_duration_seconds{event_type="WorkItemColumnChangedEvent"}
codetoreum_adapter_latency_seconds{adapter="github_board"}
codetoreum_circuit_breaker_state{service="github_api"}
```

**Configuration**:
```python
prometheus_url: str = "http://localhost:9090"
metrics_prefix: str = "codetoreum"
scrape_port: int = 8000
scrape_interval_seconds: int = 15
```

**Instrumentation**:
- Automatic instrumentation of application services
- Duration tracking for all adapter calls
- Error rate tracking per adapter
- Circuit breaker state tracking

---

### Message Distribution

#### RedisPubSubAdapter (IMessageBroker, IEventEmitter)

**Purpose**: Distribute events to subscribers via pub/sub and provide message-based communication between services.

**Implementation**:
- Pub/sub topic-based event distribution
- Persistent queue support (Redis Streams)
- Consumer groups for parallel processing
- Dead letter queue for failed messages

**Configuration**:
```python
redis_url: str = "redis://localhost:6379"
db: int = 0
ssl_verify: bool = False
event_topic_prefix: str = "events"
message_queue_prefix: str = "queues"
```

**Channels**:
- `events:*` - Domain event pub/sub
- `queues:*` - Task queues
- `notifications:*` - Real-time notifications

---

### CI/CD Integration

#### GitHubCIPipelineAdapter (ICIPipelineService)

**Purpose**: Track CI/CD pipeline status and build results via GitHub Actions.

**Implementation**:
- Queries GitHub Actions API for workflow status
- Tracks build results and test outcomes
- Polls for completion of async workflows
- Webhooks for real-time status updates

**Configuration**:
```python
token: str                      # GitHub API token
organization: str               # Organization name
repository: str                 # Repository name
polling_interval_seconds: int = 30
webhook_enabled: bool = True
```

**Workflow Tracking**:
- Monitor CI/CD run status
- Retrieve build logs
- Track test results (passed/failed/skipped)
- Detect flaky tests

**Error Handling**:
- Workflow not found → ResourceNotFoundError
- API errors → Retry with backoff
- Timeout → Resume polling on next check

---

### Repair Cycle Management

#### ProductionRepairCycleAdapter (IRepairCycle)

**Purpose**: Execute intelligent repair cycles when workflows fail, enabling test-fix-validate loops.

**Implementation**:
- Analyzes failure root cause
- Proposes repairs (code changes, config updates)
- Validates repairs with test execution
- Commits successful repairs or rolls back

**Configuration**:
```python
max_repair_attempts: int = 5        # Limit repair iterations
max_calls_per_repair: int = 100     # Prevent infinite loops
base_backoff_seconds: float = 10    # Initial backoff duration
timeout_seconds: int = 3600         # 1 hour repair timeout
```

**Repair Process**:
1. **Analyze**: Examine failure logs and context
2. **Propose**: Generate potential fixes
3. **Implement**: Apply code/config changes
4. **Validate**: Run tests to verify fix
5. **Commit** or **Rollback**: Accept or reject changes

**Events**:
- RepairCycleStartedEvent
- RepairAttemptMadeEvent
- RepairSucceededEvent
- RepairFailedEvent

---

#### ProductionEnvironmentRepairAdapter (IEnvironmentRepairService)

**Purpose**: Repair environment issues (missing dependencies, broken configuration, incompatible versions).

**Implementation**:
- Diagnoses environment problems
- Installs/updates dependencies
- Patches configuration files
- Validates repairs

**Common Repairs**:
- Missing Python packages → Install via pip
- Incompatible package versions → Resolve via dependency solver
- Missing environment variables → Create in config
- File permission errors → Fix permissions

---

### Analysis Services

#### LLMSystemicAnalysisAdapter (ISystemicAnalysisService)

**Purpose**: Use Claude Code to analyze systemic failures and recommend system-level fixes.

**Implementation**:
- Feeds failure context and logs to Claude Code
- Asks Claude to identify root causes
- Generates recommendations for fixes
- Ranks recommendations by impact

**Analysis Questions**:
- What is the root cause of this failure?
- Is this a known issue with a standard fix?
- What system changes would prevent this failure?
- Should we implement a workaround or fix the root cause?

**Integration**:
- Uses ClaudeCodeAdapter as ILLMProvider
- Supplies context (logs, error messages, system state)
- Receives structured analysis results
- Helps prioritize repair efforts

---

#### BranchResolutionAdapter (IBranchResolutionService)

**Purpose**: Intelligently resolve branch conflicts during merges.

**Implementation**:
- Detects conflicting changes
- Analyzes conflict context (code structure, intent)
- Applies conflict resolution strategies:
  - Take ours/theirs (priority-based)
  - Auto-merge (safe changes)
  - Manual review (requires human input)

**Strategies**:
1. **Ours First**: Prefer changes from main branch
2. **Recent First**: Prefer more recent changes
3. **Auto-merge**: Merge non-overlapping changes
4. **Manual Review**: Flag for human review

---

### Container Recovery

#### DockerContainerRecoveryAdapter (IAgentContainerRecoveryService)

**Purpose**: Recover from container failures (OOM, timeout, crash).

**Implementation**:
- Detects container failure conditions
- Restarts containers with adjusted resources
- Isolates flaky containers (circuit breaker)
- Escalates persistent failures

**Recovery Strategies**:
1. **Restart**: Restart container with same config
2. **Scale Up**: Increase memory/CPU limits and retry
3. **Fallback**: Route to fallback container
4. **Escalate**: Mark as requiring manual intervention

**Configuration**:
```python
max_restart_attempts: int = 3
memory_scale_factor: float = 1.5    # Increase by 50%
cpu_scale_factor: float = 1.5
circuit_breaker_threshold: int = 5  # Fail after 5 attempts
```

---

### Discussion & Comments

#### GitHubDiscussionAdapter (IDiscussionAdapter)

**Purpose**: Manage GitHub Discussions and inline comments on issues/PRs.

**Implementation**:
- Create and retrieve discussions
- Add comments to discussions
- Manage discussion categories and statuses
- Track discussion threading

**Use Cases**:
- Detailed problem discussions (separate from issues)
- Architecture decision records
- RFCs and proposals
- Knowledge base articles

---

## Testing Strategy

### Unit Tests
- Mock external service responses
- Verify correct API calls
- Test error handling and mapping
- Verify configuration handling

### Integration Tests
- Real services (via Testcontainers):
  - Elasticsearch
  - Redis
  - Prometheus
  - GitHub Actions
- End-to-end workflows
- Performance benchmarks

### Simulation Tests
- In-memory variants (InMemoryEventStore, etc.)
- Deterministic test scenarios
- Fast feedback (no external service latency)

## Resilience Patterns

All infrastructure adapters apply resilience patterns via decorators:

```python
# Adapter implementation (pure)
event_store = ElasticsearchEventStore(config)

# Resilience wrapper (infrastructure concern)
resilient_event_store = ResilientEventStoreDecorator(
    event_store,
    circuit_breaker_threshold=10,
    rate_limit=None,
    timeout_seconds=30,
    retry_count=3
)
```

**Patterns Applied**:
- **Retry**: Exponential backoff for transient errors
- **Circuit Breaker**: Stop requests after threshold of failures
- **Rate Limiting**: Respect external service rate limits
- **Timeout**: Prevent hanging requests

## Monitoring & Observability

All infrastructure adapters emit structured logs:

```python
logger.info(
    "Event stored successfully",
    extra={
        "event_id": event.id,
        "event_type": event.__class__.__name__,
        "timestamp": event.timestamp,
        "correlation_id": context.correlation_id,
    }
)
```

**Metrics Tracked**:
- Operation latency (p50, p95, p99)
- Success rate and error counts
- Circuit breaker state changes
- Queue depths and backlog

## Cross-References

- **Port Interfaces**: [Output Ports](../ports/output/) - Complete specifications
- **Bootstrap**: [Production Bootstrap](../../implementations/production-bootstrap.md) - Wiring configuration
- **Resilience**: [Resilience Patterns](../infrastructure/resilience.md) - Detailed pattern specs
- **Observability**: [Observability](../infrastructure/observability.md) - Logging and monitoring
- **Simulation**: [Simulation Adapters](../../implementations/simulation/adapters.md) - Testing alternatives
