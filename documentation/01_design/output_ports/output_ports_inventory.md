# Output Ports Inventory

## Overview

This document provides a comprehensive inventory of all output ports in the Codetoreum system redesign. Output ports define the interfaces through which the core domain interacts with external systems and infrastructure, following the Dependency Inversion Principle of hexagonal architecture.

## Output Port Categories

### 1. External System Ports
Ports for integrating with external services and systems.

| Port Name | Purpose | Primary Implementations | Status |
|-----------|---------|------------------------|--------|
| **ITicketSystem** | Issue/ticket management | GitHub Issues, Jira, Linear, In-Memory (mock) | Required |
| **ILLMProvider** | LLM integration | Claude Code, Aider, OpenAI, Mock | Required |
| **IContainer** | Container orchestration | Docker, Kubernetes, Fake (mock) | Required |
| **INotifier** | Notifications | Slack, Email, Webhooks, Mock | Optional |

### 2. Persistence Ports
Ports for data persistence and state management.

| Port Name | Purpose | Primary Implementations | Status |
|-----------|---------|------------------------|--------|
| **IRepository** | Source code management | Git, In-Memory | Required |
| **IEventStore** | Event persistence | Redis, PostgreSQL, In-Memory | Required |
| **IStorage** | File/object storage | S3, Filesystem, In-Memory | Required |
| **IConfigStore** | Configuration storage | Elasticsearch, PostgreSQL, YAML files | Required |

### 3. Observability Ports
Ports for monitoring, logging, and observability.

| Port Name | Purpose | Primary Implementations | Status |
|-----------|---------|------------------------|--------|
| **IMetrics** | Metrics collection | Elasticsearch, Prometheus, In-Memory | Required |
| **ILogger** | Structured logging | Elasticsearch, Stdout, In-Memory | Required |
| **ITracer** | Distributed tracing | OpenTelemetry, Jaeger, Mock | Optional |
| **IAuditor** | Audit logging | Elasticsearch, Database, File | Required |

## Detailed Port Descriptions

### External System Ports

#### ITicketSystem
**Description**: Interface for interacting with issue tracking and project management systems.

**Core Operations**:
- Work item CRUD (create, read, update, delete)
- Status management and transitions
- Comment operations
- Work item relationships and linking
- Webhook registration
- Search and filtering

**Key Implementations**:
- **GitHubTicketAdapter**: GitHub Issues and Projects v2 integration
- **JiraTicketAdapter**: Jira integration
- **MarkdownTicketAdapter**: Markdown file-based tickets
- **InMemoryTicketAdapter**: In-memory mock for testing

**Dependencies**: None (standalone port)

---

#### ILLMProvider
**Description**: Interface for Large Language Model provider integration.

**Core Operations**:
- Prompt execution (simple, with tools, structured output)
- Conversation management
- Streaming completions
- Code generation and review
- Token counting and usage tracking
- Model information queries

**Key Implementations**:
- **ClaudeCodeAdapter**: Anthropic Claude Code integration (containerized)
- **ClaudeProvider**: Direct Anthropic API integration
- **AiderAdapter**: Aider CLI integration
- **OpenAIProvider**: OpenAI GPT integration
- **MockLLMProvider**: Mock provider with deterministic responses for testing

**Dependencies**: IContainer (for Claude Code adapter)

---

#### IContainer
**Description**: Interface for container orchestration and execution.

**Core Operations**:
- Container lifecycle management (create, start, stop, remove)
- Container execution with volume mounts
- Environment variable management
- Network configuration
- Container status monitoring
- Log streaming

**Key Implementations**:
- **DockerContainerAdapter**: Docker integration
- **KubernetesAdapter**: Kubernetes pod management
- **FakeContainerAdapter**: Mock container for testing (simulates execution without actual containers)

**Dependencies**: None (standalone port)

---

#### INotifier
**Description**: Interface for sending notifications to external systems and users.

**Core Operations**:
- Send notifications (text, rich content)
- Channel management
- Delivery confirmation
- Template rendering
- Batch notifications

**Key Implementations**:
- **SlackNotifier**: Slack integration
- **EmailNotifier**: Email notifications
- **WebhookNotifier**: Generic webhook integration
- **MockNotifier**: Mock for testing

**Dependencies**: None (standalone port)

---

### Persistence Ports

#### IRepository
**Description**: Interface for source code repository management (Git operations).

**Core Operations**:
- Repository cloning and initialization
- Branch management (create, checkout, delete, list)
- Commit operations
- Push and pull operations
- Diff and status queries
- Merge operations
- File operations within repository

**Key Implementations**:
- **GitRepositoryAdapter**: Git CLI integration
- **InMemoryRepositoryAdapter**: Mock repository for testing

**Dependencies**: None (standalone port)

---

#### IEventStore
**Description**: Interface for event sourcing and event persistence.

**Core Operations**:
- Event appending
- Event retrieval by aggregate ID
- Event streaming
- Event replay
- Snapshot management
- Event subscription

**Key Implementations**:
- **RedisEventStore**: Redis Streams-based event store
- **PostgreSQLEventStore**: PostgreSQL-based event store
- **InMemoryEventStore**: Mock event store for testing

**Dependencies**: None (standalone port)

---

#### IStorage
**Description**: Interface for file and object storage.

**Core Operations**:
- File upload and download
- File deletion
- File listing and search
- Presigned URLs for temporary access
- Metadata management
- Directory operations

**Key Implementations**:
- **S3StorageAdapter**: AWS S3 integration
- **FilesystemStorageAdapter**: Local filesystem storage
- **InMemoryStorageAdapter**: Mock storage for testing

**Dependencies**: None (standalone port)

---

#### IConfigStore
**Description**: Interface for configuration storage and retrieval.

**Core Operations**:
- Configuration CRUD operations
- Configuration versioning
- Configuration search and filtering
- Schema validation
- Configuration export/import

**Key Implementations**:
- **ElasticsearchConfigStore**: Elasticsearch-based configuration storage
- **PostgreSQLConfigStore**: PostgreSQL-based configuration storage
- **YAMLConfigStore**: YAML file-based configuration (legacy)
- **InMemoryConfigStore**: Mock configuration store for testing

**Dependencies**: None (standalone port)

---

### Observability Ports

#### IMetrics
**Description**: Interface for metrics collection and reporting.

**Core Operations**:
- Counter increments
- Gauge updates
- Histogram recording
- Timer operations
- Custom metric recording
- Metric queries and aggregation

**Key Implementations**:
- **ElasticsearchMetrics**: Elasticsearch-based metrics
- **PrometheusMetrics**: Prometheus integration
- **InMemoryMetrics**: Mock metrics for testing

**Dependencies**: None (standalone port)

---

#### ILogger
**Description**: Interface for structured logging.

**Core Operations**:
- Log message emission (debug, info, warn, error)
- Structured field attachment
- Context propagation
- Log level management
- Log querying and search

**Key Implementations**:
- **ElasticsearchLogger**: Elasticsearch-based logging
- **StdoutLogger**: Standard output logging
- **InMemoryLogger**: Mock logger for testing

**Dependencies**: None (standalone port)

---

#### ITracer
**Description**: Interface for distributed tracing.

**Core Operations**:
- Span creation and management
- Trace context propagation
- Span annotation
- Trace export
- Sampling configuration

**Key Implementations**:
- **OpenTelemetryTracer**: OpenTelemetry integration
- **JaegerTracer**: Jaeger integration
- **MockTracer**: Mock tracer for testing

**Dependencies**: None (standalone port)

---

#### IAuditor
**Description**: Interface for audit logging and compliance tracking.

**Core Operations**:
- Audit event recording
- Audit trail queries
- Compliance report generation
- Event retention management
- Audit event search and filtering

**Key Implementations**:
- **ElasticsearchAuditor**: Elasticsearch-based audit logging
- **DatabaseAuditor**: Database-based audit logging
- **FileAuditor**: File-based audit logging
- **InMemoryAuditor**: Mock auditor for testing

**Dependencies**: None (standalone port)

---

## Port Dependencies

Most output ports are standalone with no dependencies on other ports. However, some adapters may have cross-dependencies:

- **ClaudeCodeAdapter** (ILLMProvider) → **IContainer**: Claude Code runs in containerized environments
- Various adapters may use **ILogger** and **IMetrics** for internal logging and metrics

## Testing Strategy

Each output port should have:

1. **Contract Tests**: Abstract test class that validates port contract compliance
2. **Mock Implementations**: In-memory implementations for fast unit testing
3. **Integration Tests**: Tests against real implementations (with appropriate test fixtures)

## Implementation Priority

### Phase 1 (MVP)
- ITicketSystem (GitHub adapter)
- ILLMProvider (Claude Code adapter)
- IContainer (Docker adapter)
- IRepository (Git adapter)
- IEventStore (Redis adapter)
- ILogger (Elasticsearch adapter)
- IMetrics (Elasticsearch adapter)

### Phase 2 (Enhanced Testing)
- All mock/in-memory adapters
- Contract test framework

### Phase 3 (Extended Integrations)
- ITicketSystem (Jira, Linear adapters)
- ILLMProvider (Aider, OpenAI adapters)
- INotifier (Slack, Email adapters)
- IStorage (S3, Filesystem adapters)

### Phase 4 (Advanced Observability)
- ITracer (OpenTelemetry adapter)
- IAuditor (Enhanced audit logging)

## Notes

- All output ports follow the Dependency Inversion Principle - the core domain depends on port interfaces, not implementations
- Adapters are swappable through dependency injection
- Mock implementations enable full system testing without external dependencies
- Port interfaces are technology-agnostic and don't expose implementation details
