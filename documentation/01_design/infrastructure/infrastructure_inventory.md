# Infrastructure Components - Inventory

## Overview

This document provides an inventory of all infrastructure components in the Codetoreum Gen 2 system. Infrastructure components are **cross-cutting concerns** that support the entire application but are not part of the core domain logic.

## Infrastructure Categories

### 1. Resilience Infrastructure

**Purpose**: Provide production-grade resilience patterns for all external system integrations.

**Location**: `documentation/01_design/infrastructure/resilience_infrastructure_design.md`

**Components**:
- **Rate Limiters**
  - `IRateLimiter` - Interface
  - `TokenBucketRateLimiter` - Production implementation (sliding window)
  - `SlidingWindowRateLimiter` - Alternative production implementation
  - `MockRateLimiter` - Simulation/testing implementation

- **Circuit Breakers**
  - `ICircuitBreaker` - Interface
  - `CircuitBreaker` - Production implementation (CLOSED/OPEN/HALF_OPEN states)
  - `MockCircuitBreaker` - Simulation/testing implementation

- **Retry Policies**
  - `IRetryPolicy` - Interface
  - `ExponentialBackoffRetry` - Production implementation (with jitter)
  - `MockRetryPolicy` - Simulation/testing implementation

- **Timeouts**
  - `ITimeout` - Interface
  - `AsyncTimeout` - Production implementation
  - `MockTimeout` - Simulation/testing implementation

- **Resilient Decorators** (compose resilience patterns)
  - `ResilientTicketSystemDecorator` - Wraps ITicketSystem
  - `ResilientLLMProviderDecorator` - Wraps ILLMProvider
  - `ResilientRepositoryDecorator` - Wraps IRepository
  - `ResilientContainerDecorator` - Wraps IContainer

- **Factories**
  - `ResilienceFactory` - Creates resilient adapters with appropriate components
  - `OperationMode` - Enum: PRODUCTION, SIMULATION, INTEGRATION_TEST

**Key Features**:
- Prevents cascading failures
- Respects API rate limits (request-based and token-based)
- Handles transient errors
- Prevents hung operations
- Enables observability
- Supports simulation testing

---

### 2. Event Store Infrastructure

**Purpose**: Persist and query domain events for event sourcing and audit trails.

**Location**: `documentation/01_design/secondary_adapters/infrastructure_adapters_design.md` (lines 523-899)

**Components**:
- `IEventStore` - Port interface
- `ElasticsearchEventStore` - Production implementation with Redis buffering
- `EventPersistenceWorker` - Background worker for async persistence
- `InMemoryEventStore` - Testing/simulation implementation

**Architecture**:
- **Write Path**: Events → Redis Stream (immediate ack) → Background worker → Elasticsearch (durable)
- **Read Path**: Elasticsearch queries (with slight lag)
- **Benefits**: High write throughput, data durability, event replay, full-text search

---

### 3. Configuration Storage Infrastructure

**Purpose**: Store and retrieve application configuration with versioning and search.

**Location**: `documentation/01_design/secondary_adapters/infrastructure_adapters_design.md` (lines 902-1119)

**Components**:
- `IConfigStore` - Port interface
- `ElasticsearchConfigStore` - Production implementation with Redis caching
- `InMemoryConfigStore` - Testing/simulation implementation

**Architecture**:
- **Write Path**: Write-through cache (Elasticsearch + Redis + pub/sub invalidation)
- **Read Path**: Redis cache (< 1ms) → Elasticsearch fallback
- **Features**: Versioning, full-text search, configuration history

---

### 4. Repository Infrastructure

**Purpose**: Abstract Git repository operations.

**Location**: `documentation/01_design/secondary_adapters/infrastructure_adapters_design.md` (lines 15-297)

**Components**:
- `IRepository` - Port interface
- `GitRepositoryAdapter` - Production implementation (Git CLI)
- `InMemoryRepositoryAdapter` - Testing/simulation implementation

**Operations**:
- Clone, checkout, commit, push, pull
- Branch management
- Branch status checking (ahead/behind, conflicts)

---

### 5. Container Runtime Infrastructure

**Purpose**: Abstract container execution (Docker).

**Location**: `documentation/01_design/secondary_adapters/infrastructure_adapters_design.md` (lines 299-519)

**Components**:
- `IContainer` - Port interface
- `DockerContainerAdapter` - Production implementation
- `FakeContainerAdapter` - Testing/simulation implementation

**Features**:
- Container execution with streaming output
- Image building and management
- Volume mounting and environment variables

---

### 6. Metrics & Observability Infrastructure

**Purpose**: Collect and report system metrics.

**Location**:
- `documentation/01_design/output_ports/imetrics_design.md`
- `documentation/01_design/secondary_adapters/infrastructure_adapters_design.md` (lines 1172-1218)

**Components**:
- `IMetrics` - Port interface
- `ElasticsearchMetrics` - Production implementation
- `PrometheusMetrics` - Alternative production implementation
- `InMemoryMetrics` - Testing/simulation implementation

**Metrics Types**:
- Counters (total events)
- Gauges (current values)
- Histograms (distributions)
- Timers (operation durations)

---

### 7. Logging Infrastructure

**Purpose**: Structured logging with correlation IDs and context.

**Location**: `documentation/01_design/output_ports/ilogger_design.md`

**Components**:
- `ILogger` - Port interface
- `StructuredLogger` - Production implementation (JSON logs)
- `ConsoleLogger` - Development implementation
- `InMemoryLogger` - Testing implementation

**Features**:
- Log levels (DEBUG, INFO, WARNING, ERROR, CRITICAL)
- Contextual logging (correlation IDs, user IDs, agent IDs)
- Structured output (JSON for log aggregation)

---

### 8. Notification Infrastructure

**Purpose**: Send notifications to users and external systems.

**Location**:
- `documentation/01_design/output_ports/inotifier_design.md`
- `documentation/01_design/secondary_adapters/infrastructure_adapters_design.md` (lines 1220-1255)

**Components**:
- `INotifier` - Port interface
- `EmailNotifier` - Production implementation
- `SlackNotifier` - Production implementation
- `ConsoleNotifier` - Development implementation
- `InMemoryNotifier` - Testing implementation

**Notification Types**:
- Success/failure alerts
- Review requests
- System health alerts

---

### 9. Storage Infrastructure

**Purpose**: Generic key-value storage abstraction.

**Location**: `documentation/01_design/secondary_adapters/infrastructure_adapters_design.md` (lines 1123-1170)

**Components**:
- `IStorage` - Port interface
- `FileSystemStorage` - Local filesystem implementation
- `S3Storage` - Cloud storage implementation (future)
- `InMemoryStorage` - Testing implementation

**Use Cases**:
- Artifact storage
- Temporary file management
- Configuration backups

---

### 10. Tracing Infrastructure

**Purpose**: Distributed tracing for request flow analysis.

**Location**: `documentation/01_design/output_ports/itracer_design.md`

**Components**:
- `ITracer` - Port interface
- `JaegerTracer` - Production implementation (OpenTelemetry)
- `InMemoryTracer` - Testing implementation

**Features**:
- Span creation and context propagation
- Distributed trace correlation
- Performance analysis

---

### 11. Auditing Infrastructure

**Purpose**: Audit trail for security and compliance.

**Location**: `documentation/01_design/output_ports/iauditor_design.md`

**Components**:
- `IAuditor` - Port interface
- `DatabaseAuditor` - Production implementation
- `InMemoryAuditor` - Testing implementation

**Audit Events**:
- User actions (create, update, delete)
- Authentication events
- Configuration changes
- Administrative actions

---

## Infrastructure Patterns

### Decorator Pattern

All resilience concerns are applied via **decorators** that wrap adapters:

```
ITicketSystem (interface)
    ↓ implements
GitHubTicketAdapter (pure adapter)
    ↓ wrapped by
ResilientTicketSystemDecorator
    ↓ uses
[RateLimiter, CircuitBreaker, RetryPolicy, Timeout]
```

**Benefits**:
- Separation of concerns
- Adapter remains pure (no resilience code)
- Composable (mix and match patterns)
- Testable (each component independently)

### Factory Pattern

`ResilienceFactory` creates adapters with appropriate components based on **operation mode**:

- **PRODUCTION**: Real implementations (TokenBucketRateLimiter, CircuitBreaker, etc.)
- **SIMULATION**: Mock implementations (no delays, just tracking)
- **INTEGRATION_TEST**: Mix of real and mock (enforce limits but fast)

### Strategy Pattern

Each infrastructure concern has:
- **Interface** (e.g., `IRateLimiter`)
- **Production implementations** (e.g., `TokenBucketRateLimiter`, `SlidingWindowRateLimiter`)
- **Mock implementations** (e.g., `MockRateLimiter`)

Swappable at composition time via dependency injection.

---

## Infrastructure Dependencies

### External Dependencies

- **Elasticsearch**: Event store, config store, metrics
- **Redis**: Event buffering, config caching, rate limiting state
- **Docker**: Container runtime
- **Prometheus** (optional): Metrics aggregation
- **Jaeger** (optional): Distributed tracing
- **PostgreSQL** (optional): Audit logs, configuration

### Internal Dependencies

Infrastructure components depend on:
- **Port interfaces** (from `src/ports/output/`)
- **Domain events** (from `src/domain/events/`)
- **Value objects** (from `src/domain/value_objects/`)

Infrastructure does **NOT** depend on:
- Domain models (pure business logic)
- Application services
- Other infrastructure components (loosely coupled)

---

## Testing Strategy

### Unit Tests
- Test each infrastructure component in isolation
- Mock external dependencies (Elasticsearch, Redis, Docker)
- Focus on component logic and state management

### Integration Tests
- Test infrastructure with real external systems
- Use testcontainers for ephemeral dependencies
- Verify correct integration with external APIs

### Simulation Tests
- Use mock infrastructure implementations
- Test full application workflows without external dependencies
- Fast, deterministic, reproducible

### Contract Tests
- Verify adapters correctly implement port interfaces
- Ensure production and mock implementations have same behavior
- Catch interface breaking changes

---

## Configuration

### Service-Specific Configuration

Each service (GitHub, Claude, etc.) has dedicated resilience configuration:

```yaml
services:
  github:
    resilience:
      rate_limit:
        max_requests: 5000
        window_seconds: 3600
      circuit_breaker:
        failure_threshold: 5
        timeout_seconds: 60
      retry:
        max_retries: 3
        base_delay: 1.0

  claude:
    resilience:
      rate_limit:
        max_requests: 50
        window_seconds: 60
        max_tokens: 40000
      circuit_breaker:
        failure_threshold: 3
        timeout_seconds: 120
      retry:
        max_retries: 2
        base_delay: 2.0
```

### Global Configuration

```yaml
infrastructure:
  mode: production  # production | simulation | integration_test

  event_store:
    type: elasticsearch
    elasticsearch_url: "http://localhost:9200"
    redis_url: "redis://localhost:6379"

  config_store:
    type: elasticsearch
    cache_ttl: 3600

  metrics:
    type: prometheus
    endpoint: "http://localhost:9090"

  tracing:
    type: jaeger
    endpoint: "http://localhost:14268"
```

---

## Migration Strategy

### Phase 1: Core Resilience (Current)
1. Implement resilience interfaces and components
2. Create production implementations (rate limiter, circuit breaker, retry, timeout)
3. Create mock implementations for simulation
4. Build resilient decorators for each port
5. Create resilience factory

### Phase 2: Event Store & Configuration
1. Implement Elasticsearch event store with Redis buffering
2. Implement Elasticsearch config store with Redis caching
3. Deploy background workers for event persistence
4. Migrate from YAML files to database-backed config

### Phase 3: Observability
1. Implement metrics collection (Prometheus)
2. Implement distributed tracing (Jaeger)
3. Implement structured logging
4. Build observability dashboard

### Phase 4: Additional Infrastructure
1. Implement notification system
2. Implement audit logging
3. Implement storage abstraction
4. Add monitoring and alerting

---

## Summary

The infrastructure layer provides:

1. **Resilience patterns** - Circuit breakers, rate limiting, retries, timeouts
2. **Event sourcing** - Event store with replay capability
3. **Configuration management** - Versioned, searchable configuration
4. **Observability** - Metrics, logging, tracing, auditing
5. **External system abstractions** - Repository, container, storage
6. **Testing support** - Mock implementations for simulation mode

All infrastructure is:
- **Adapter-agnostic** - Works with any port implementation
- **Composable** - Mix and match components
- **Testable** - Production and mock implementations
- **Observable** - Built-in metrics and statistics
- **Configurable** - Per-service and global configuration
