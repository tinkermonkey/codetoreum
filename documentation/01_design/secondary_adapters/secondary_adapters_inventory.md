# Secondary Adapters Inventory

## Overview

Secondary adapters are implementations of the **Output Ports** defined in the hexagonal architecture. They connect the core application domain to external systems and infrastructure. The redesign emphasizes having both **production** and **testing/mock** implementations for each adapter to support comprehensive testing and simulation capabilities.

## Adapter Categories

Based on the high-level architecture and legacy system analysis, secondary adapters are organized into the following categories:

1. **Ticket System Adapters** - Connect to issue tracking systems
2. **LLM Provider Adapters** - Connect to AI/LLM services
3. **Repository Adapters** - Connect to code repository systems
4. **Container Runtime Adapters** - Connect to containerization platforms
5. **Event Store Adapters** - Connect to event storage systems
6. **Metrics & Observability Adapters** - Connect to monitoring and metrics systems
7. **Storage Adapters** - Connect to file and data storage systems
8. **Notification Adapters** - Connect to notification services

---

## 1. Ticket System Adapters

### 1.1 GitHub Issues Adapter (Production)

**Purpose**: Connect to GitHub Issues for work item management

**Interface**: `ITicketSystem`

**Key Capabilities**:
- Retrieve work items (issues)
- Update work item status and labels
- Create comments on issues
- Manage project board cards
- Query issue hierarchy (parent/sub-issues)

**Dependencies**: GitHub REST API, GitHub GraphQL API

**Configuration**:
- GitHub token or App authentication
- Repository organization and name
- Project board IDs

---

### 1.2 Jira Adapter (Production)

**Purpose**: Connect to Jira for work item management

**Interface**: `ITicketSystem`

**Key Capabilities**:
- Retrieve Jira tickets
- Update ticket status
- Create comments
- Manage workflow transitions

**Status**: Planned for extensibility

---

### 1.3 Markdown File Adapter (Production)

**Purpose**: Use markdown files in a folder as work items

**Interface**: `ITicketSystem`

**Key Capabilities**:
- Read markdown files as work items
- Parse YAML front matter for metadata
- Update file content
- File-based state management

**Status**: Planned for extensibility

---

### 1.4 In-Memory Ticket Adapter (Testing/Mock)

**Purpose**: Provide in-memory ticket system for testing and simulation

**Interface**: `ITicketSystem`

**Key Capabilities**:
- Store work items in memory
- Simulate ticket lifecycle
- Pre-populate test scenarios
- No external dependencies

**Use Cases**:
- Unit testing
- Integration testing
- End-to-end simulation
- Local development

---

## 2. LLM Provider Adapters

### 2.1 Claude Code Adapter (Production)

**Purpose**: Execute Claude via Claude Code CLI in containerized environments

**Interface**: `ILLMProvider`

**Key Capabilities**:
- Execute prompts with context
- Stream responses in real-time
- Manage conversational sessions
- Handle tool use and MCP servers
- Track token usage

**Dependencies**: Claude Code CLI, Docker

**Configuration**:
- CLAUDE_CODE_OAUTH_TOKEN or ANTHROPIC_API_KEY
- Model selection
- MCP server configurations

---

### 2.2 Aider Adapter (Production)

**Purpose**: Execute prompts using Aider for code editing

**Interface**: `ILLMProvider`

**Status**: Planned for extensibility

---

### 2.3 GPT-4 Adapter (Production)

**Purpose**: Execute prompts using OpenAI GPT-4

**Interface**: `ILLMProvider`

**Status**: Planned for extensibility

---

### 2.4 Mock LLM Adapter (Testing/Mock)

**Purpose**: Provide deterministic LLM responses for testing

**Interface**: `ILLMProvider`

**Key Capabilities**:
- Return predetermined responses based on prompt patterns
- Simulate streaming behavior
- No API calls or costs
- Configurable response delays
- Response template support

**Use Cases**:
- Unit testing agent logic
- Integration testing workflows
- Simulation scenarios
- Performance testing

---

## 3. Repository Adapters

### 3.1 Git Repository Adapter (Production)

**Purpose**: Manage local Git repositories and remote operations

**Interface**: `IRepository`

**Key Capabilities**:
- Clone repositories
- Create and manage branches
- Commit changes with proper attribution
- Push to remote
- Pull and rebase operations
- Detect merge conflicts
- Handle SSH authentication

**Dependencies**: Git CLI, SSH keys

**Configuration**:
- Repository URL
- SSH key path
- Git config (user.name, user.email)

---

### 3.2 In-Memory Repository Adapter (Testing/Mock)

**Purpose**: Simulate Git operations without actual filesystem or network operations

**Interface**: `IRepository`

**Key Capabilities**:
- Simulate branch creation
- Track simulated commits
- Mock merge conflicts
- No filesystem I/O
- Instant operations

**Use Cases**:
- Unit testing workspace logic
- Testing branch management
- Simulating conflict scenarios

---

## 4. Container Runtime Adapters

### 4.1 Docker Container Adapter (Production)

**Purpose**: Execute agents in Docker containers

**Interface**: `IContainer`

**Key Capabilities**:
- Build Docker images from Dockerfile.agent
- Run containers with volume mounts
- Stream container logs
- Manage container lifecycle
- Handle Docker-in-Docker scenarios
- Track containers in Redis

**Dependencies**: Docker daemon, Docker socket access

**Configuration**:
- Docker image tags
- Volume mount paths
- Network configuration
- Environment variables

---

### 4.2 Fake Container Adapter (Testing/Mock)

**Purpose**: Simulate container execution without Docker

**Interface**: `IContainer`

**Key Capabilities**:
- Simulate container runs
- Mock container logs
- Instant execution (no startup overhead)
- No Docker daemon required
- Configurable exit codes and outputs

**Use Cases**:
- Unit testing agent executor
- CI/CD environments without Docker
- Rapid testing iterations

---

## 5. Event Store Adapters

### 5.1 Redis Event Store (Production)

**Purpose**: Store and stream events using Redis Streams

**Interface**: `IEventStore`

**Key Capabilities**:
- Append domain events
- Query events by time range
- Pub/sub for real-time delivery
- Event replay capabilities
- TTL-based retention

**Dependencies**: Redis server

**Configuration**:
- Redis host and port
- Stream key names
- Retention policies

---

### 5.2 Elasticsearch Event Store (Production)

**Purpose**: Store events in Elasticsearch for advanced querying and analytics

**Interface**: `IEventStore`

**Key Capabilities**:
- Index events with full-text search
- Complex queries and aggregations
- Time-series analysis
- Daily index rotation
- Long-term retention

**Dependencies**: Elasticsearch cluster

**Configuration**:
- Elasticsearch URL
- Index patterns
- Mapping templates

---

### 5.3 In-Memory Event Store (Testing/Mock)

**Purpose**: Store events in memory for testing

**Interface**: `IEventStore`

**Key Capabilities**:
- Append events to in-memory list
- Query by filters
- No external dependencies
- Fast access
- Test scenario pre-population

**Use Cases**:
- Unit testing event sourcing
- Verifying event emissions
- Testing event replay logic

---

## 6. Metrics & Observability Adapters

### 6.1 Elasticsearch Metrics Adapter (Production)

**Purpose**: Send metrics to Elasticsearch for storage and analysis

**Interface**: `IMetrics`

**Key Capabilities**:
- Record task metrics (duration, success rate)
- Record quality metrics
- Index with timestamps
- Daily index rotation
- Aggregation support

**Dependencies**: Elasticsearch cluster

---

### 6.2 In-Memory Metrics Adapter (Testing/Mock)

**Purpose**: Collect metrics in memory for testing

**Interface**: `IMetrics`

**Key Capabilities**:
- Store metrics in memory
- Query metrics for assertions
- No external dependencies
- Reset between tests

**Use Cases**:
- Unit testing metrics collection
- Verifying metric values
- Performance testing without I/O overhead

---

## 7. Storage Adapters

### 7.1 File System Storage Adapter (Production)

**Purpose**: Store configuration and state on local filesystem

**Interface**: `IStorage`

**Key Capabilities**:
- Read/write YAML files
- JSON file operations
- Directory management
- File locking for concurrent access

**Configuration**:
- Base directory paths
- File permissions

---

### 7.2 Database Storage Adapter (Production)

**Purpose**: Store configuration in database (replacing YAML files)

**Interface**: `IStorage`

**Key Capabilities**:
- Store project configurations
- Store agent configurations
- Version configuration changes
- Web UI for management

**Dependencies**: Database (e.g., PostgreSQL, or Elasticsearch)

**Status**: Planned for configuration migration

---

### 7.3 In-Memory Storage Adapter (Testing/Mock)

**Purpose**: Store data in memory for testing

**Interface**: `IStorage`

**Key Capabilities**:
- Read/write to memory structures
- No filesystem I/O
- Fast operations
- Reset between tests

---

## 8. Notification Adapters

### 8.1 GitHub Notifier (Production)

**Purpose**: Send notifications via GitHub (comments, labels, status updates)

**Interface**: `INotifier`

**Key Capabilities**:
- Post comments to issues/discussions
- Update labels
- Set issue status
- Format notifications with markdown

**Dependencies**: GitHub API

---

### 8.2 Email Notifier (Production)

**Purpose**: Send email notifications

**Interface**: `INotifier`

**Status**: Planned for extensibility

---

### 8.3 Slack Notifier (Production)

**Purpose**: Send notifications to Slack channels

**Interface**: `INotifier`

**Status**: Planned for extensibility

---

### 8.4 Console Notifier (Testing/Mock)

**Purpose**: Log notifications to console for testing

**Interface**: `INotifier`

**Key Capabilities**:
- Print notifications to stdout
- No external service dependencies
- Useful for debugging

---

## Summary

### Production Adapters (Currently Implemented or Planned)

1. **GitHub Issues Adapter** - Primary ticket system
2. **Claude Code Adapter** - Primary LLM provider
3. **Git Repository Adapter** - Version control
4. **Docker Container Adapter** - Agent execution
5. **Redis Event Store** - Real-time event streaming
6. **Elasticsearch Event Store** - Event indexing and analytics
7. **Elasticsearch Metrics Adapter** - Metrics storage
8. **File System Storage Adapter** - Current configuration storage
9. **GitHub Notifier** - Primary notification channel

### Testing/Mock Adapters (Needed for Redesign Goals)

1. **In-Memory Ticket Adapter** - For testing without GitHub
2. **Mock LLM Adapter** - For deterministic testing
3. **In-Memory Repository Adapter** - For testing without Git
4. **Fake Container Adapter** - For testing without Docker
5. **In-Memory Event Store** - For testing event sourcing
6. **In-Memory Metrics Adapter** - For testing metrics
7. **In-Memory Storage Adapter** - For testing configuration
8. **Console Notifier** - For testing notifications

### Extensibility Targets (Future)

1. **Jira Adapter** - Alternative ticket system
2. **Markdown File Adapter** - File-based ticket system
3. **Aider Adapter** - Alternative LLM provider
4. **GPT-4 Adapter** - Alternative LLM provider
5. **Database Storage Adapter** - For web-based configuration
6. **Email Notifier** - Additional notification channel
7. **Slack Notifier** - Additional notification channel

---

## Design Principles for Secondary Adapters

### 1. Interface Segregation
Each adapter implements a focused interface (e.g., `ITicketSystem`, `ILLMProvider`) with a clear contract.

### 2. Production/Test Pairs
Every production adapter has a corresponding mock/in-memory adapter for testing without external dependencies.

### 3. Configuration via Dependency Injection
All adapters receive their configuration through constructor injection, making them easy to instantiate with different settings.

### 4. Stateless Design
Adapters should be stateless where possible, with state managed by the core domain or explicit state services.

### 5. Error Handling
Adapters translate external system errors into domain-specific exceptions that the core can handle appropriately.

### 6. Observability
All adapter operations emit events to the observability system for tracking and debugging.

### 7. Pluggable Architecture
Adapters are registered in a registry that allows runtime selection based on configuration.
