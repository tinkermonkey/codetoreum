# External Systems Inventory

This document provides a complete inventory of all external systems that the redesigned Codetoreum platform will integrate with.

## Overview

The Codetoreum platform relies on five core external systems to provide its functionality. These systems handle various aspects of the platform's operation, from code execution and version control to persistence and observability.

## External System Categories

### 1. AI & Code Execution
- **Claude API**: AI model provider for agent intelligence and code generation

### 2. Version Control & Project Management
- **GitHub API**: Source code hosting, issue tracking, project boards, and webhooks

### 3. Container Orchestration
- **Docker**: Container runtime for agent isolation and execution environment management

### 4. Data Persistence & Caching
- **Redis**: High-speed caching, task queuing, event streaming, and session state management
- **Elasticsearch**: Event indexing, metrics storage, historical analysis, and search capabilities

## System-by-System Inventory

### 1. GitHub API

**Purpose**: Version control, issue tracking, project management, and webhook-driven automation

**Integration Points**:
- Repository management (clone, pull, push)
- Issue and pull request operations
- Project boards (GitHub Projects v2)
- Discussions
- Webhooks for event notifications
- GitHub App authentication
- GraphQL and REST APIs

**Critical Dependencies**:
- All git-based workflows
- Issue-driven task creation
- Project board monitoring
- Code change tracking
- Team collaboration features

**Redesign Considerations**:
- Pluggable ticket system architecture (GitHub Issues, Jira, Markdown files)
- Abstraction layer for repository operations
- Mock implementation for testing

---

### 2. Claude API

**Purpose**: AI-powered code generation, analysis, and agent intelligence

**Integration Points**:
- Claude CLI for agent execution
- Anthropic API for direct model access
- Streaming responses
- Session continuity
- Token usage tracking
- Model selection (Sonnet, Opus variants)

**Critical Dependencies**:
- All agent executions
- Code generation and modification
- Analysis and reasoning tasks
- Conversational interactions
- Review and feedback loops

**Redesign Considerations**:
- Pluggable LLM provider architecture (Claude, GPT-4, Aider, etc.)
- Mock LLM adapter for testing and simulation
- Deterministic response mode for end-to-end testing
- Context management and prompt construction abstraction

---

### 3. Docker

**Purpose**: Container runtime for isolated agent execution environments

**Integration Points**:
- Docker daemon via socket (/var/run/docker.sock)
- Container lifecycle management (create, start, stop, remove)
- Image building and management
- Volume mounts for workspace isolation
- Network configuration for service connectivity
- Docker Compose for orchestration

**Critical Dependencies**:
- Agent container execution
- Development environment setup
- Repair cycle containers
- Workspace isolation
- Dependency management

**Redesign Considerations**:
- Container execution abstraction
- Mock container adapter for testing
- Lightweight alternatives for local development
- Security isolation improvements (rootless Docker consideration)

---

### 4. Redis

**Purpose**: High-performance data structure store for caching, queuing, and real-time data

**Integration Points**:
- Task queue (sorted sets)
- Event streaming (pub/sub channels)
- Event history (streams)
- Container tracking (key-value with TTL)
- Execution state tracking
- Conversational session state
- Health status caching

**Data Structures Used**:
- **Sorted Sets**: Priority-based task queue
- **Pub/Sub**: Real-time event streaming
- **Streams**: Event history with retention
- **Strings with TTL**: Execution state, container tracking
- **Hashes**: Complex state objects

**Critical Dependencies**:
- Task queueing system
- Real-time observability
- Container recovery logic
- Execution deduplication
- Session continuity

**Redesign Considerations**:
- Abstract queue interface for pluggable implementations
- In-memory queue for testing
- Persistent queue for production reliability
- Backup mechanisms for queue durability

---

### 5. Elasticsearch

**Purpose**: Distributed search and analytics engine for events, metrics, and historical data

**Integration Points**:
- Daily indices for events and metrics
- Decision event storage and analysis
- Agent execution history
- Metrics aggregation and visualization
- Pattern detection and alerting
- Full-text search capabilities

**Index Types**:
- `decision-events-YYYY-MM-DD`: Decision tracking
- `agent-events-YYYY-MM-DD`: Agent lifecycle events
- `orchestrator-task-metrics-YYYY.MM.DD`: Task performance metrics
- `orchestrator-quality-metrics-YYYY.MM.DD`: Quality measurements
- `pipeline-runs-YYYY-MM-DD`: Pipeline execution tracking
- `review-filters`: Review issue filter patterns

**Critical Dependencies**:
- Observability and monitoring
- Historical analysis
- Pattern detection
- Metrics visualization
- Debug and troubleshooting
- Configuration storage (review filters)

**Redesign Considerations**:
- Database-driven configuration (moving from YAML to Elasticsearch/database)
- Web UI for configuration management
- Query abstraction for analytics
- Mock storage for testing
- Alternative backends (PostgreSQL, MongoDB)

---

## External System Dependencies Matrix

| System | Used By | Purpose | Can Be Mocked? |
|--------|---------|---------|----------------|
| GitHub API | Project Monitor, Workspace Context, Git Workflow Manager | Repository operations, issue management, project boards | Yes - InMemoryTicketAdapter |
| Claude API | All Agents, Claude Integration | AI intelligence, code generation | Yes - MockLLMProvider |
| Docker | Agent Executor, Docker Runner, Repair Cycle Runner | Container isolation, execution environment | Partially - FakeContainerAdapter |
| Redis | Task Queue, Observability, State Tracking, Session State | Queuing, caching, real-time events | Yes - InMemoryQueue/Storage |
| Elasticsearch | Observability Manager, Metrics Collector, Decision Analytics | Event indexing, metrics, analytics | Yes - InMemoryEventStore |

## Integration Patterns

### 1. Adapter Pattern
All external system integrations use the adapter pattern to enable:
- Swappable implementations
- Mock versions for testing
- Easy migration to alternative systems
- Clear interface boundaries

### 2. Port-Adapter Architecture (Hexagonal)
External systems connect through:
- **Output Ports**: Interfaces defining operations (e.g., `ITicketSystem`, `ILLMProvider`)
- **Secondary Adapters**: Concrete implementations (e.g., `GitHubTicketAdapter`, `ClaudeCodeAdapter`)
- **Mock Adapters**: Test implementations (e.g., `InMemoryTicketAdapter`, `MockLLMProvider`)

### 3. Configuration-Driven
External system connections are:
- Configurable via environment variables
- Support multiple authentication methods
- Fail gracefully with clear error messages
- Provide health check endpoints

## Authentication & Credentials

### GitHub API
- **GitHub App**: JWT-based authentication with installation tokens
- **Personal Access Token**: Simple token-based auth
- **OAuth**: For user-facing operations

### Claude API
- **OAuth Token**: Subscription-based access (CLAUDE_CODE_OAUTH_TOKEN)
- **API Key**: Pay-per-use access (ANTHROPIC_API_KEY)

### Docker
- **Socket Access**: /var/run/docker.sock (requires user in docker group)
- **TLS**: For remote Docker daemon (future consideration)

### Redis
- **No Auth** (default): For development
- **Password**: For production environments
- **TLS**: For encrypted connections

### Elasticsearch
- **No Auth** (default): For development
- **Basic Auth**: Username/password
- **API Key**: For production
- **TLS**: For encrypted connections

## Health & Monitoring

Each external system requires health checks:
- **GitHub API**: Rate limit status, API reachability
- **Claude API**: Authentication validity, model availability
- **Docker**: Daemon connectivity, image availability
- **Redis**: Ping response, memory usage
- **Elasticsearch**: Cluster health, index status

Health check results stored in Redis with TTL for fast access.

## Failure Modes & Recovery

### GitHub API
- **Rate Limiting**: Exponential backoff, request queuing
- **API Downtime**: Retry logic, fallback to local operations
- **Authentication Failure**: Clear error messages, token refresh

### Claude API
- **Token Exhaustion**: Rate limiting, quota management
- **Model Unavailability**: Fallback to alternative models
- **Timeout**: Configurable timeouts, partial result handling

### Docker
- **Daemon Unreachable**: Clear error, recovery instructions
- **Image Pull Failure**: Retry logic, local cache
- **Container Startup Failure**: Cleanup, diagnostic logging

### Redis
- **Connection Lost**: In-memory fallback, reconnection logic
- **Memory Full**: Eviction policies, monitoring alerts
- **Data Loss**: Backup to filesystem, recovery procedures

### Elasticsearch
- **Cluster Unavailable**: Queue events in Redis, bulk replay
- **Index Full**: Automatic rollover, retention policies
- **Query Timeout**: Simplified queries, caching

## Redesign Impact

### Current State
- Direct coupling to specific external systems
- Limited testability without real services
- YAML-based configuration
- Manual recovery procedures

### Target State
- Abstract interfaces for all external systems
- Full mock implementations for testing
- Database/Elasticsearch-driven configuration
- Web UI for configuration management
- Automatic recovery and health monitoring
- Simulation mode with no external dependencies

## Summary

The platform integrates with 5 core external systems, each serving a critical role:
1. **GitHub API** - Version control and project management
2. **Claude API** - AI intelligence and code generation
3. **Docker** - Container isolation and execution
4. **Redis** - High-speed caching and queuing
5. **Elasticsearch** - Event indexing and analytics

All systems will be abstracted through ports and adapters to enable:
- Easy testing with mocks
- Swappable implementations
- Graceful degradation
- Clear failure modes
- Health monitoring
- Simulation mode operation
