# Implementation Plan: Codetoreum Generation 2

## Overview

This document provides a detailed, phased implementation plan for building Codetoreum Generation 2 based on the Hexagonal Architecture with Event Sourcing described in `02_high_level_arch.md`. The plan prioritizes testability, simulation capabilities, and incremental delivery.

## Persistence Architecture

**Primary Storage: Elasticsearch**
- Events (event sourcing)
- Logs (application and execution logs)
- Configuration (projects, workflows, agents)
- Metrics (historical analysis)

**Buffering & Caching: Redis**
- Event buffering before Elasticsearch persistence
- Configuration caching for fast access
- Real-time pub/sub for event handlers
- Task queue management

**Data Flow Pattern:**
```
Application → Redis (buffer/cache) → Background Workers → Elasticsearch (persistence)
```

This architecture provides:
- High write throughput via Redis buffering
- Fast reads via Redis caching
- Full-text search capabilities via Elasticsearch
- Time-series data management via index lifecycle management
- Reliable delivery via Redis consumer groups

## Implementation Principles

1. **Incremental Development**: Each phase delivers working, testable functionality
2. **Test-First Approach**: Write tests before or alongside implementation
3. **Parallel Tracks**: Multiple components can be developed concurrently
4. **Backward Compatibility**: Maintain ability to fall back to Gen 1 during transition
5. **Documentation-Driven**: Keep design docs updated as implementation progresses

## Phase Overview

- **Phase 1**: Foundation & Core Domain
- **Phase 2**: Port Interfaces & Basic Adapters
- **Phase 3**: Event Sourcing Infrastructure
- **Phase 4**: Mock Adapters & Simulation Mode
- **Phase 5**: Application Services
- **Phase 6**: Primary Adapters & API Layer
- **Phase 7**: Configuration System
- **Phase 8**: Migration & Integration
- **Phase 9**: Production Hardening

---

## Phase 1: Foundation & Core Domain

### Objectives

- Establish project structure and tooling
- Implement core domain models with no external dependencies
- Set up testing framework
- Define domain events taxonomy

### Deliverables

#### 1.1 Project Setup

- [ ] Create new Python project structure with hexagonal architecture layout
  ```
  codetoreum/
  ├── src/
  │   ├── domain/              # Core business logic
  │   ├── application/         # Application services
  │   ├── ports/              # Port interfaces
  │   ├── adapters/           # Adapter implementations
  │   │   ├── primary/        # Inbound adapters
  │   │   └── secondary/      # Outbound adapters
  │   └── infrastructure/     # Cross-cutting concerns
  ├── tests/
  │   ├── unit/
  │   ├── integration/
  │   └── simulation/
  └── docs/
  ```
- [ ] Set up dependency management (Poetry)
- [ ] Configure linting (ruff, mypy, black)
- [ ] Set up testing framework (pytest, pytest-asyncio, pytest-cov)
- [ ] Set up code coverage reporting (minimum 80% for domain layer)

#### 1.2 Domain Models

**Priority 1: Core Entities**

- [ ] Implement `WorkItem` aggregate root (see `domains/work_item_design.md`)

  - Properties: id, title, description, status, metadata
  - Methods: assign_to_agent(), transition_status(), add_comment()
  - Domain events: WorkItemCreated, WorkItemAssigned, WorkItemStatusChanged
  - Unit tests with 100% coverage

- [ ] Implement `Agent` entity (see `domains/agent_design.md`)

  - Properties: id, name, type, capabilities, configuration
  - Methods: can_handle(), validate_configuration()
  - Domain events: AgentConfigured
  - Unit tests with 100% coverage

- [ ] Implement `AgentExecution` aggregate root (see `domains/agent_execution_design.md`)
  - Properties: id, agent, work_item, context, status, results
  - Methods: start(), complete(), fail(), add_artifact()
  - Domain events: ExecutionStarted, ExecutionCompleted, ExecutionFailed
  - Unit tests with 100% coverage

**Priority 2: Workflow Entities**

- [ ] Implement `PipelineStage` entity (see `domains/pipeline_stage_design.md`)

  - Properties: id, name, stage_type, agent_config, entry_conditions
  - Methods: can_enter(), get_agent_for_execution()
  - Unit tests with 100% coverage

- [ ] Implement `Workflow` aggregate root (see `domains/workflow_design.md`)

  - Properties: id, name, stages, current_stage
  - Methods: add_stage(), advance_to_next_stage(), get_current_stage()
  - Domain events: WorkflowStageAdvanced
  - Unit tests with 100% coverage

- [ ] Implement `WorkflowTemplate` entity (see `domains/workflow_template_design.md`)
  - Properties: id, name, description, stage_templates
  - Methods: instantiate_workflow(), validate()
  - Unit tests with 100% coverage

**Priority 3: Context & Review Entities**

- [ ] Implement `ProjectContext` value object (see `domains/project_context_design.md`)

  - Properties: project_id, repository_url, branch, dependencies
  - Immutable value object pattern
  - Unit tests with 100% coverage

- [ ] Implement `WorkspaceContext` value object (see `domains/workspace_context_design.md`)

  - Properties: workspace_id, mounted_files, environment_variables
  - Immutable value object pattern
  - Unit tests with 100% coverage

- [ ] Implement `ReviewCycle` entity (see `domains/review_cycle_design.md`)
  - Properties: id, execution_id, reviewer, status, feedback
  - Methods: submit_feedback(), approve(), request_changes()
  - Domain events: ReviewRequested, ReviewCompleted
  - Unit tests with 100% coverage

#### 1.3 Value Objects & Enumerations

- [ ] Implement value objects (see `domains/value_objects_design.md`)
  - ExecutionStatus enum (PENDING, RUNNING, COMPLETED, FAILED, CANCELLED)
  - WorkItemStatus enum (NEW, IN_PROGRESS, IN_REVIEW, COMPLETED, BLOCKED)
  - AgentType enum (REQUIREMENTS_ANALYST, ARCHITECT, DEVELOPER, REVIEWER, etc.)
  - ExecutionResult value object (status, artifacts, metrics, logs)
  - ContainerConfig value object (image, volumes, environment)

#### 1.4 Domain Events

- [ ] Create base `DomainEvent` class

  - Properties: event_id, timestamp, aggregate_id, event_type, version
  - Serialization/deserialization methods

- [ ] Implement all domain events (see `domains/domain_events_design.md`)

  - WorkItem events: Created, Assigned, StatusChanged, Commented
  - Execution events: Started, Completed, Failed, ArtifactGenerated
  - Workflow events: StageAdvanced, WorkflowCompleted
  - Review events: ReviewRequested, ReviewCompleted, FeedbackSubmitted

- [ ] Unit tests for all domain events
  - Serialization/deserialization
  - Event equality and hashing
  - Event versioning

#### 1.5 Domain Services

- [ ] Implement domain services (see `domains/domain_services_design.md`)

  - AgentSelector: Logic for selecting appropriate agent based on stage/work item
  - WorkflowProgressValidator: Validate stage transitions
  - ExecutionContextBuilder: Build execution context from project and workspace

- [ ] Unit tests for all domain services

### Success Criteria

- [ ] All domain models implemented with no external dependencies
- [ ] 100% unit test coverage for domain layer
- [ ] All domain events defined and tested
- [ ] Domain models can be instantiated and manipulated in memory

### Risks & Mitigations

- **Risk**: Domain model too complex or poorly designed
  - **Mitigation**: Regular design reviews, refactoring sprints, maintain design docs
- **Risk**: Testing overhead slows development
  - **Mitigation**: Use test generators, parameterized tests, and fixtures

---

## Phase 2: Port Interfaces & Basic Adapters

### Objectives

- Define all port interfaces (contracts between core and adapters)
- Implement infrastructure resilience layer (circuit breakers, rate limiting, retries, timeouts)
- Implement production adapters for critical external systems
- Implement basic in-memory adapters for testing

### Deliverables

#### 2.1 Output Port Interfaces

**See `output_ports/` directory for detailed designs**

- [ ] Define `ITicketSystem` interface

  - Methods: get_work_item(), update_work_item(), create_comment(), list_work_items()
  - See `output_ports/ticket_system_port.md`

- [ ] Define `ILLMProvider` interface

  - Methods: execute_prompt(), stream_response(), get_usage_metrics()
  - See `output_ports/llm_provider_port.md`

- [ ] Define `IRepository` interface

  - Methods: clone(), checkout(), commit(), push(), get_file_content()
  - See `output_ports/repository_port.md`

- [ ] Define `IContainer` interface

  - Methods: run(), run_async(), get_logs(), stop(), cleanup()
  - See `output_ports/container_port.md`

- [ ] Define `IEventStore` interface

  - Methods: append(), get_events(), get_stream(), replay()
  - See `output_ports/event_store_port.md`

- [ ] Define `IStorage` interface

  - Methods: store_artifact(), retrieve_artifact(), list_artifacts(), delete_artifact()
  - See `output_ports/storage_port.md`

- [ ] Define `IMetrics` interface

  - Methods: record_metric(), increment_counter(), record_duration(), query()
  - See `output_ports/metrics_port.md`

- [ ] Define `INotifier` interface
  - Methods: send_notification(), send_email(), post_webhook()
  - See `output_ports/notifier_port.md`

#### 2.2 Input Port Interfaces

**See `input_ports/` directory for detailed designs**

- [ ] Define `IWorkflowCommand` interface

  - Methods: create_workflow(), start_execution(), cancel_execution()
  - See `input_ports/workflow_command_port.md`

- [ ] Define `ITaskQuery` interface

  - Methods: get_execution_status(), list_executions(), get_artifacts()
  - See `input_ports/task_query_port.md`

- [ ] Define `IConfigCommand` interface
  - Methods: update_workflow(), update_agent_config(), update_project_config()
  - See `input_ports/config_command_port.md`

#### 2.3 Infrastructure Resilience Layer

**See `infrastructure/resilience_infrastructure_design.md`**

- [ ] Define resilience component interfaces

  - `IRateLimiter` interface (request and token-based rate limiting)
  - `ICircuitBreaker` interface (prevent cascading failures)
  - `IRetryPolicy` interface (exponential backoff with jitter)
  - `ITimeout` interface (async timeout management)

- [ ] Implement production resilience components

  - `TokenBucketRateLimiter` (requests per time window)
  - `SlidingWindowRateLimiter` (token-based for LLM APIs)
  - `CircuitBreaker` (CLOSED/OPEN/HALF_OPEN state machine)
  - `ExponentialBackoffRetry` (configurable retry logic)
  - `AsyncTimeout` (per-operation timeouts)
  - Unit tests for all components

- [ ] Implement simulation resilience components

  - `MockRateLimiter` (no delays, enforces limits in simulation)
  - `MockCircuitBreaker` (controllable state for testing)
  - `MockRetryPolicy` (immediate retries without delays)
  - `MockTimeout` (instant timeouts for fast tests)
  - Unit tests for all mock components

- [ ] Implement resilient adapter decorators

  - `ResilientTicketSystemDecorator` (wraps ITicketSystem)
  - `ResilientLLMProviderDecorator` (wraps ILLMProvider)
  - `ResilientRepositoryDecorator` (wraps IRepository)
  - `ResilientContainerDecorator` (wraps IContainer)
  - `ResilientEventStoreDecorator` (wraps IEventStore)
  - Composable decorators (mix and match patterns)
  - Integration tests with mock adapters

- [ ] Implement resilience factory

  - `ResilientAdapterFactory` (creates wrapped adapters based on mode)
  - Configuration-driven resilience policies
  - Modes: PRODUCTION, SIMULATION, INTEGRATION_TEST
  - Service-specific configurations (GitHub: 5000/hr, Claude: 50/min)

#### 2.4 Production Secondary Adapters

**See `secondary_adapters/` directory for detailed designs**

- [ ] Implement `GitHubTicketAdapter` (Priority 1)

  - Uses GitHub API for issues and project boards
  - Polling mechanism for detecting card movements
  - Webhook support for real-time updates
  - See `secondary_adapters/ticket_system_adapters_design.md`
  - Integration tests with mock GitHub API

- [ ] Implement `ClaudeCodeAdapter` (Priority 1)

  - Interfaces with Claude Code API/CLI
  - Streaming response support
  - Token usage tracking
  - See `secondary_adapters/llm_provider_adapters_design.md`
  - Integration tests with mock Claude API

- [ ] Implement `DockerContainerAdapter` (Priority 1)

  - Docker SDK for Python integration
  - Volume mounting for project files and context
  - Environment variable injection
  - Container lifecycle management
  - See `secondary_adapters/infrastructure_adapters_design.md`
  - Integration tests with Docker testcontainers

- [ ] Implement `GitRepositoryAdapter` (Priority 2)

  - GitPython or pygit2 integration
  - Clone, checkout, commit, push operations
  - Branch management
  - See `secondary_adapters/infrastructure_adapters_design.md`
  - Integration tests with temporary repositories

- [ ] Implement `S3StorageAdapter` (Priority 2)
  - AWS S3 integration for artifact storage
  - Streaming upload/download support
  - See `secondary_adapters/infrastructure_adapters_design.md`
  - Integration tests with LocalStack

#### 2.5 Testing Adapters

- [ ] Implement `InMemoryTicketAdapter`

  - Simple dictionary-based storage
  - Useful for unit and integration tests

- [ ] Implement `MockLLMAdapter`

  - Predefined responses based on prompt patterns
  - Configurable delays for simulation

- [ ] Implement `FakeContainerAdapter`

  - Simulates container execution without Docker
  - Returns predefined results

- [ ] Implement `InMemoryRepositoryAdapter`

  - In-memory file system simulation

- [ ] Implement `InMemoryEventStore`
  - Simple list-based event storage
  - Supports replay for testing

#### 2.6 Adapter Registry & Factory

- [ ] Implement adapter registries for each port type

  - TicketSystemRegistry
  - LLMProviderRegistry
  - ContainerRegistry

- [ ] Implement adapter factory pattern

  - Configuration-driven adapter instantiation
  - Dependency injection support

- [ ] Integration tests for adapter swapping

### Success Criteria

- [ ] All port interfaces defined with comprehensive documentation
- [ ] Infrastructure resilience layer implemented and tested
- [ ] Resilient adapter decorators working for all port types
- [ ] Critical production adapters implemented and tested
- [ ] In-memory/mock adapters available for all ports
- [ ] Adapter registry and factory working
- [ ] Resilience factory creating adapters based on mode
- [ ] Integration tests passing for all adapters

### Risks & Mitigations

- **Risk**: External API changes break adapters
  - **Mitigation**: Version pinning, adapter versioning, abstraction layers
- **Risk**: Docker dependency complicates testing
  - **Mitigation**: Testcontainers, mock adapters

---

## Phase 3: Event Sourcing Infrastructure

### Objectives

- Build event store infrastructure for persistence and replay
- Implement event handlers and projections
- Create event streaming capabilities with Redis buffering
- Build event replay and debugging tools
- Establish data flow: Application → Redis (buffer) → Elasticsearch (persistence)

### Deliverables

#### 3.1 Event Store Implementation

**See `external_systems/elasticsearch_design.md` and `output_ports/event_store_port.md`**

**Data Flow Architecture:**
```
Application → Redis Streams (buffer) → Background Workers → Elasticsearch (persistent storage)
                    ↓
              In-Memory Event Bus (for real-time event handlers)
```

- [ ] Implement `ElasticsearchEventStore` (Production)

  - Index design: events-{YYYY.MM} with mappings for id, aggregate_id, event_type, data, timestamp, version
  - Efficient querying by aggregate ID, timestamp, event type using Elasticsearch queries
  - Optimistic concurrency control using version field
  - Index lifecycle management for retention
  - Integration tests with Elasticsearch testcontainer

- [ ] Implement `RedisEventBuffer` (Buffering Layer)

  - Redis Streams for buffering events before Elasticsearch persistence
  - Consumer groups for reliable delivery to Elasticsearch
  - Configurable batch size and flush intervals
  - Failure handling and retry logic
  - Monitoring of buffer depth and throughput
  - Dual-purpose: buffer for persistence AND pub/sub for real-time handlers

- [ ] Implement background workers for Elasticsearch persistence

  - Consumer processes that read from Redis Streams
  - Batch insertion to Elasticsearch for efficiency
  - Error handling with dead letter queue
  - Monitoring and alerting for lag

- [ ] Implement event serialization
  - JSON serialization with schema versioning
  - Support for backward/forward compatibility
  - Compression for large events
  - Elasticsearch document mapping

#### 3.2 Event Publishing & Subscription

- [ ] Implement `EventBus` for in-process event handling

  - Pub/sub pattern for event handlers
  - Async event dispatching
  - Error handling and retry logic

- [ ] Implement event handler registry

  - Decorator-based handler registration
  - Handler ordering and dependencies

- [ ] Create base `EventHandler` class
  - Handle method for processing events
  - Error handling and logging

#### 3.3 Event Projections

- [ ] Implement read model projections

  - Execution status projection (current state of executions)
  - Workflow progress projection (current state of workflows)
  - Work item projection (current state of work items)

- [ ] Implement projection rebuilding

  - Replay all events to rebuild projections
  - Useful for schema changes and debugging

- [ ] Integration tests for projections

#### 3.4 Event Replay & Debugging Tools

- [ ] Implement `EventReplayer` service

  - Replay events from specific timestamp
  - Replay events for specific aggregate
  - Replay with time manipulation for testing

- [ ] Build CLI tool for event inspection

  - List events by aggregate, type, timestamp
  - Pretty-print event data
  - Search events by content

- [ ] Build event visualization dashboard (basic)
  - Timeline view of events
  - Aggregate event stream view
  - Event statistics

### Success Criteria

- [ ] Event store implementations working and tested
- [ ] Events persisted and retrievable
- [ ] Event replay working correctly
- [ ] Projections updating in real-time from events
- [ ] Event debugging tools available

### Risks & Mitigations

- **Risk**: Event schema evolution breaks replay
  - **Mitigation**: Schema versioning, migration strategies, comprehensive tests
- **Risk**: Event store performance issues
  - **Mitigation**: Indexing, caching, partitioning, load testing

---

## Phase 4: Mock Adapters & Simulation Mode

### Objectives

- Complete all mock/in-memory adapters
- Build simulation runner infrastructure
- Create test scenarios for end-to-end validation
- Enable fast, deterministic testing

### Deliverables

#### 4.1 Complete Mock Adapter Suite

- [ ] Enhance `MockLLMAdapter`

  - Response templates based on agent type
  - Simulated streaming with configurable delays
  - Token usage simulation
  - Failure scenarios (timeouts, rate limits)

- [ ] Enhance `FakeContainerAdapter`

  - Simulated file system operations
  - Configurable execution duration
  - Exit code simulation
  - Log generation

- [ ] Implement `InMemoryMetricsAdapter`

  - Store metrics in memory
  - Query support for testing
  - Reset capability

- [ ] Implement `MockNotifierAdapter`
  - Capture notifications for verification
  - No actual email/webhook sending

#### 4.2 Simulation Infrastructure

- [ ] Implement `SimulationClock`

  - Time manipulation for testing
  - Speed multiplier for fast-forward
  - Deterministic time progression

- [ ] Implement `SimulationConfig`

  - Configuration for mock adapter behavior
  - Scenario-specific settings
  - Time scaling settings

- [ ] Implement `SimulationRunner`
  - Orchestrates simulation scenarios
  - Sets up all mock adapters
  - Runs scenario events
  - Verifies outcomes
  - Generates simulation report

#### 4.3 Test Scenarios

- [ ] Create scenario DSL or YAML format

  - Define initial state (work items, workflows)
  - Define sequence of events (card movements, API calls)
  - Define expected outcomes (assertions)

- [ ] Implement basic scenarios

  - **Scenario 1**: Simple workflow (1 work item, 3 stages, 3 agents)
  - **Scenario 2**: Parallel executions (multiple work items)
  - **Scenario 3**: Review cycle with feedback loop
  - **Scenario 4**: Execution failure and retry
  - **Scenario 5**: Complex workflow with branches

- [ ] Implement scenario runner
  - Load scenarios from files
  - Execute scenarios
  - Report results

#### 4.4 Simulation Testing Framework

- [ ] Create pytest fixtures for simulation mode

  - Automatic mock adapter injection
  - Simulation clock injection
  - Scenario loading fixtures

- [ ] Create simulation test helpers

  - Assertions for domain events
  - Assertions for projection state
  - Time advancement helpers

- [ ] Write simulation tests for all scenarios
  - End-to-end tests using simulation mode
  - Fast execution (seconds, not minutes)
  - Deterministic results

### Success Criteria

- [ ] All mock adapters complete and tested
- [ ] Simulation runner working for all scenarios
- [ ] Test scenarios defined and passing
- [ ] Simulation mode 10-100x faster than real execution
- [ ] Deterministic test results (no flakiness)

### Risks & Mitigations

- **Risk**: Mock behavior diverges from production
  - **Mitigation**: Regular validation against production, contract tests
- **Risk**: Scenarios too simplistic to catch real issues
  - **Mitigation**: Add scenarios based on production incidents, continuous expansion

---

## Phase 5: Application Services

### Objectives

- Implement orchestration and coordination logic
- Build application services that use domain models and ports
- Implement workflow execution engine
- Create agent scheduling and execution logic

### Deliverables

#### 5.1 Core Application Services

**See `application_services/` directory for detailed designs**

- [ ] Implement `WorkflowOrchestrator`

  - Handle card movement events
  - Determine next stage in workflow
  - Coordinate with AgentScheduler
  - Emit workflow events
  - Integration tests with mock adapters

- [ ] Implement `AgentScheduler`
  - Queue executions for agents
  - Handle execution prioritization
  - Coordinate with ExecutionService
  - Integration tests with mock adapters

#### 5.2 Execution Services

- [ ] Implement `ExecutionService`

  - Create agent executions
  - Coordinate with container and LLM adapters
  - Manage execution lifecycle (start, monitor, complete)
  - Handle execution failures and retries
  - Stream execution logs
  - Integration tests with mock adapters

- [ ] Implement `ContextBuilder`
  - Gather all context for execution
  - Fetch work item details
  - Fetch project context
  - Build workspace context
  - Write context files for container mounting
  - Unit and integration tests

#### 5.3 Review Services

- [ ] Implement `ReviewService`

  - Create review cycles
  - Assign reviewers
  - Process review feedback
  - Determine if re-execution needed
  - Handle approval workflow
  - Integration tests with mock adapters

- [ ] Implement `FeedbackProcessor`
  - Parse review feedback
  - Extract actionable items
  - Create new work items if needed
  - Integration tests

#### 5.4 Workspace & Pipeline Services

- [ ] Implement `WorkspaceRouter`

  - Manage container workspaces
  - Handle file mounting
  - Coordinate repository operations
  - Manage environment variables
  - Integration tests with mock adapters

- [ ] Implement `PipelineManager`
  - Execute multi-stage pipelines
  - Coordinate stage transitions
  - Handle stage dependencies
  - Emit pipeline events
  - Integration tests with mock adapters

#### 5.5 Configuration Service

- [ ] Implement `ConfigurationService`
  - Load and cache configurations
  - Validate configurations
  - Support configuration updates
  - Emit configuration change events
  - Integration tests with mock adapters

#### 5.6 Event Processing

- [ ] Implement event handlers for all application services

  - WorkflowEventHandler
  - ExecutionEventHandler
  - ReviewEventHandler

- [ ] Wire up event bus to application services

  - Register all handlers
  - Configure handler dependencies
  - Error handling and retry logic

- [ ] End-to-end integration tests
  - Test full event flow from card movement to execution completion
  - Use mock adapters
  - Verify all events emitted correctly
  - Verify projections updated correctly

### Success Criteria

- [ ] All application services implemented and tested
- [ ] Services can orchestrate full workflows using domain models
- [ ] Event-driven architecture working end-to-end
- [ ] Integration tests passing with mock adapters
- [ ] Services can run in simulation mode

### Risks & Mitigations

- **Risk**: Services too tightly coupled
  - **Mitigation**: Regular refactoring, dependency analysis, code reviews
- **Risk**: Complex orchestration logic hard to test
  - **Mitigation**: State machines, extensive simulation tests, event replay

---

## Phase 6: Primary Adapters & API Layer

### Objectives

- Implement inbound adapters (webhooks, REST API, CLI)
- Build API layer for external access
- Create dashboard for monitoring and control
- Implement authentication and authorization

### Deliverables

#### 6.1 Webhook Adapter

**See `primary_adapters/github_webhook_adapter.md`**

- [ ] Implement `GitHubWebhookAdapter`

  - FastAPI endpoint for GitHub webhooks
  - Webhook signature verification
  - Parse webhook payloads
  - Translate to domain events
  - Handle various event types (project_card, issue, pull_request)
  - Integration tests with mock webhook payloads

- [ ] Implement webhook retry and error handling
  - Idempotency checks
  - Error responses
  - Webhook event logging

#### 6.2 REST API

**See `primary_adapters/rest_api_adapter.md`**

- [ ] Set up FastAPI application

  - OpenAPI documentation
  - Request validation with Pydantic
  - Error handling middleware
  - CORS configuration

- [ ] Implement command endpoints

  - POST /api/workflows - Create workflow
  - POST /api/workflows/{id}/start - Start execution
  - POST /api/workflows/{id}/cancel - Cancel execution
  - POST /api/configurations - Update configuration

- [ ] Implement query endpoints

  - GET /api/workflows - List workflows
  - GET /api/workflows/{id} - Get workflow details
  - GET /api/executions - List executions
  - GET /api/executions/{id} - Get execution details
  - GET /api/executions/{id}/logs - Stream execution logs
  - GET /api/work-items - List work items
  - GET /api/work-items/{id} - Get work item details

- [ ] Integration tests for all endpoints
  - Request/response validation
  - Authentication checks
  - Error handling

#### 6.3 WebSocket API

**See `primary_adapters/websocket_api_adapter.md`**

- [ ] Implement WebSocket endpoint for real-time updates

  - Connection management
  - Authentication
  - Subscribe to execution streams
  - Subscribe to workflow progress
  - Broadcast events to subscribed clients

- [ ] Implement event streaming

  - Transform domain events to API events
  - Filter events by subscription
  - Handle backpressure

- [ ] Integration tests for WebSocket API

#### 6.4 CLI Adapter

**See `primary_adapters/cli_adapter.md`**

- [ ] Implement CLI using Click or Typer

  - Command structure mirroring API
  - Authentication via token
  - Configuration file support

- [ ] Implement CLI commands

  - `codetoreum workflow create` - Create workflow
  - `codetoreum workflow start` - Start execution
  - `codetoreum workflow list` - List workflows
  - `codetoreum execution list` - List executions
  - `codetoreum execution logs` - Stream logs
  - `codetoreum config update` - Update configuration

- [ ] CLI tests

#### 6.5 Authentication & Authorization

- [ ] Implement authentication

  - JWT token-based authentication
  - API key support
  - Token refresh mechanism

- [ ] Implement authorization

  - Role-based access control (RBAC)
  - Permission checks on endpoints
  - Project-level access control

- [ ] Security tests
  - Authentication bypass attempts
  - Authorization escalation attempts
  - Token validation

#### 6.6 Basic Web Dashboard

- [ ] Create simple web UI (React or Vue)

  - Workflow list and details view
  - Execution list and details view
  - Real-time log streaming
  - Work item list and details view

- [ ] Connect to REST and WebSocket APIs

  - API client integration
  - Real-time updates via WebSocket

- [ ] Basic E2E tests with Playwright or Cypress

### Success Criteria

- [ ] All primary adapters implemented and tested
- [ ] REST API fully functional with OpenAPI docs
- [ ] WebSocket API streaming events in real-time
- [ ] CLI working for all major operations
- [ ] Authentication and authorization working
- [ ] Basic web dashboard operational

### Risks & Mitigations

- **Risk**: API design doesn't meet user needs
  - **Mitigation**: Early API design reviews, user feedback, iterative design
- **Risk**: Real-time streaming performance issues
  - **Mitigation**: Load testing, backpressure handling, rate limiting

---

## Phase 7: Configuration System

### Objectives

- Replace YAML files with Elasticsearch-backed configuration
- Build web UI for configuration management with search capabilities
- Implement configuration versioning and rollback
- Support project-specific and global configurations
- Enable full-text search across all configurations

### Deliverables

#### 7.1 Configuration Index Schema

- [ ] Design Elasticsearch indices

  - `config-projects` index for project configurations
  - `config-workflows` index for workflow definitions
  - `config-workflow-stages` index for stage configurations
  - `config-agents` index for agent configurations
  - `config-environment` index for environment variables
  - `config-history` index for configuration change audit trail
  - Define mappings for all fields (nested objects for complex configs)

- [ ] Implement index templates and settings

  - Index templates for consistent mapping across indices
  - Analyzers for configuration search capabilities
  - Retention policies using ILM

#### 7.2 Configuration Storage Adapter

- [ ] Implement `ElasticsearchConfigStorage`

  - CRUD operations for all configuration entities
  - Complex queries using Elasticsearch DSL
  - Optimistic concurrency control
  - Full-text search capabilities for configuration discovery
  - Integration tests with Elasticsearch testcontainer

- [ ] Implement `RedisConfigCache` (Buffering Layer)
  - Redis-backed cache for frequently accessed configurations
  - Write-through cache for configuration updates
  - Cache invalidation on updates (pub/sub pattern)
  - TTL-based expiration with automatic refresh
  - Monitoring of cache hit rates

#### 7.3 Configuration Service Enhancement

- [ ] Enhance `ConfigurationService`

  - Elasticsearch-backed storage
  - Configuration validation
  - Configuration versioning
  - Audit trail for changes (stored in config-history index)
  - Rollback capability using historical documents
  - Full-text search across configurations

- [ ] Implement configuration templates
  - Pre-built workflow templates
  - Pre-configured agent types
  - Easy instantiation for new projects
  - Template search and discovery using Elasticsearch queries

#### 7.4 Configuration Web UI

- [ ] Create configuration management pages

  - Project configuration page
    - Environment variables management
    - Mounted commands and sub-agents
    - Repository settings
  - Workflow configuration page
    - Add/edit/delete stages
    - Configure stage transitions
    - Assign agents to stages
  - Agent configuration page
    - Edit agent prompts
    - Configure agent capabilities
    - Set agent constraints

- [ ] Implement configuration forms with validation

  - Form fields for all configuration options
  - Client-side and server-side validation
  - Real-time preview of changes

- [ ] Implement configuration history view

  - List all configuration changes
  - Diff view for changes
  - Rollback functionality

- [ ] E2E tests for configuration UI

#### 7.5 Migration from YAML

- [ ] Build YAML import tool

  - Parse existing YAML configurations
  - Validate against schema
  - Import into Elasticsearch indices
  - Generate migration report

- [ ] Test migration with existing configurations

  - Verify all data migrated correctly
  - Validate behavior unchanged
  - Test search and query capabilities

- [ ] Documentation for configuration management

### Success Criteria

- [ ] Elasticsearch indices designed and implemented
- [ ] Configuration stored in Elasticsearch, not YAML files
- [ ] Redis caching layer operational
- [ ] Web UI for configuration management working
- [ ] Configuration versioning and rollback working
- [ ] Full-text search capabilities working
- [ ] Existing YAML configurations migrated successfully

### Risks & Mitigations

- **Risk**: Migration breaks existing configurations
  - **Mitigation**: Thorough testing, parallel run mode, rollback plan
- **Risk**: Configuration UI too complex for users
  - **Mitigation**: User testing, iterative design, comprehensive help docs

---

## Phase 8: Migration & Integration

### Objectives

- Integrate Gen 2 with existing Gen 1 system
- Migrate existing workloads to Gen 2
- Run parallel mode for validation
- Complete cutover to Gen 2

### Deliverables

#### 8.1 Integration Planning

- [ ] Map Gen 1 components to Gen 2 architecture

  - Identify overlapping functionality
  - Identify Gen 1 components to deprecate
  - Identify Gen 1 components to maintain during transition

- [ ] Design integration approach

  - **Option A**: Parallel run (both systems active)
  - **Option B**: Phased migration (project-by-project)
  - **Option C**: Big bang migration (full cutover)
  - **Recommendation**: Phased migration with parallel run for validation

- [ ] Create migration plan document
  - Timeline for migration
  - Risk assessment
  - Rollback procedures

#### 8.2 Integration Layer

- [ ] Implement Gen 1 compatibility layer

  - Adapter to translate Gen 1 events to Gen 2 domain events
  - Adapter to translate Gen 2 events back to Gen 1 format
  - Dual-write to both Gen 1 and Gen 2 data stores

- [ ] Implement feature flags

  - Flag to enable/disable Gen 2 for specific projects
  - Flag to enable parallel mode (run both systems)
  - Flag to enable Gen 2-only mode

- [ ] Integration tests for compatibility layer

#### 8.3 Pilot Migration

- [ ] Select pilot project

  - Low-risk project
  - Representative of typical usage
  - Active development for good testing

- [ ] Migrate pilot project configuration

  - Import configuration to Gen 2 Elasticsearch indices
  - Validate configuration
  - Set up monitoring

- [ ] Run pilot project on Gen 2

  - Enable feature flag
  - Monitor for issues
  - Compare behavior to Gen 1

- [ ] Validate pilot project
  - Verify all workflows execute correctly
  - Verify all events captured
  - Verify performance acceptable
  - Gather user feedback

#### 8.4 Parallel Run & Validation

- [ ] Enable parallel run for all projects

  - Both Gen 1 and Gen 2 process events
  - Compare outputs and behavior
  - Log discrepancies

- [ ] Build comparison tools

  - Compare execution results
  - Compare event sequences
  - Compare performance metrics

- [ ] Analyze discrepancies

  - Investigate differences
  - Fix bugs in Gen 2
  - Update tests to prevent regressions

- [ ] Performance testing
  - Load testing with production-like workload
  - Identify bottlenecks
  - Optimize hot paths

#### 8.5 Full Migration

- [ ] Migrate all projects to Gen 2

  - Project-by-project migration
  - Validate each migration
  - Gather feedback

- [ ] Disable Gen 1 event processing

  - Keep Gen 1 as read-only for historical data
  - All new events processed by Gen 2 only

- [ ] Monitor for issues
  - Enhanced monitoring during cutover
  - On-call rotation for quick response
  - Rollback plan ready

#### 8.6 Decommissioning Gen 1

- [ ] Archive Gen 1 data

  - Export historical data
  - Store in long-term archive

- [ ] Decommission Gen 1 services

  - Graceful shutdown
  - Remove from infrastructure
  - Update documentation

- [ ] Clean up codebase
  - Remove Gen 1 code
  - Remove compatibility layer
  - Remove feature flags

### Success Criteria

- [ ] All projects migrated to Gen 2
- [ ] Gen 1 decommissioned
- [ ] No critical issues or rollbacks
- [ ] Performance meets or exceeds Gen 1
- [ ] User feedback positive

### Risks & Mitigations

- **Risk**: Critical bug discovered after cutover
  - **Mitigation**: Thorough testing, parallel run, gradual rollout, rollback plan
- **Risk**: Performance regression
  - **Mitigation**: Load testing, performance benchmarks, optimization
- **Risk**: User resistance to change
  - **Mitigation**: Training, documentation, user feedback loop

---

## Phase 9: Production Hardening

### Objectives

- Harden system for production reliability
- Implement comprehensive monitoring and alerting
- Optimize performance
- Improve operational tooling

### Deliverables

#### 9.1 Reliability Improvements

**Note**: Infrastructure resilience layer (circuit breakers, rate limiting, retries, timeouts) is implemented in Phase 2. This phase focuses on production configuration and monitoring.

- [ ] Configure resilience policies for production

  - GitHub API: 5000 requests/hour, circuit breaker (5 failures in 1 min)
  - Claude API: 50 requests/minute, token-based rate limiting
  - Docker operations: 10 concurrent containers, 30s timeout
  - Elasticsearch: Circuit breaker (10 failures in 5 min), 10s timeout
  - Redis: Circuit breaker (5 failures in 30s), 5s timeout

- [ ] Configure retry policies for production

  - Exponential backoff: 1s, 2s, 4s, 8s, 16s (max 5 retries)
  - Jitter: +/- 20% randomization to prevent thundering herd
  - Dead letter queue for permanently failed events
  - Configurable per-service based on API characteristics

- [ ] Implement health checks
  - Liveness probe (service is running)
  - Readiness probe (service can handle requests)
  - Dependency health checks (Elasticsearch, Redis, GitHub, Claude)
  - Circuit breaker status checks
  - Rate limiter status checks

#### 9.2 Monitoring & Observability

- [ ] Implement structured logging

  - Contextual logging with trace IDs
  - Log levels appropriate for production
  - Sensitive data redaction
  - Logs streamed to Elasticsearch via Redis buffer
  - Index pattern: logs-{YYYY.MM.DD} for time-based retention

- [ ] Implement metrics collection

  - Execution metrics (duration, success rate, etc.)
  - System metrics (CPU, memory, etc.)
  - Business metrics (workflows completed, work items processed, etc.)
  - **Resilience metrics** (NEW):
    - Circuit breaker state changes and trip counts
    - Rate limiter utilization and throttle events
    - Retry attempts and failure rates
    - Timeout occurrences
    - Per-service health status
  - Metrics stored in Elasticsearch for historical analysis
  - Integration with Prometheus/Grafana for real-time monitoring
  - Redis for metrics buffering and aggregation

- [ ] Implement distributed tracing

  - OpenTelemetry integration
  - Trace execution flow across services
  - Traces stored in Elasticsearch
  - Integration with Jaeger or Kibana APM

- [ ] Create monitoring dashboards
  - Kibana dashboards for logs, events, and metrics
  - System health dashboard
  - Execution metrics dashboard
  - Business metrics dashboard
  - **Resilience dashboard** (NEW):
    - Circuit breaker status per service
    - Rate limiter utilization trends
    - Retry attempt distribution
    - Timeout occurrence heatmap
    - Service health matrix
  - Grafana dashboards for real-time metrics

#### 9.3 Alerting

- [ ] Define alert conditions

  - Execution failures above threshold
  - System errors above threshold
  - Performance degradation
  - Dependency failures
  - **Resilience alerts** (NEW):
    - Circuit breaker trips (OPEN state)
    - Rate limiter saturation (> 90% utilization)
    - Excessive retry attempts (> 50% of requests)
    - Frequent timeout occurrences (> 10% of requests)
    - Service health degradation

- [ ] Implement alerting

  - Integration with PagerDuty or similar
  - Alert routing based on severity
  - Alert aggregation to reduce noise

- [ ] Create runbooks for alerts
  - Troubleshooting steps
  - Resolution procedures
  - Escalation paths
  - **Resilience runbooks** (NEW):
    - Circuit breaker recovery procedures
    - Rate limit adjustment guidelines
    - Retry policy tuning
    - Timeout configuration guidance
    - Service health check debugging

#### 9.4 Performance Optimization

- [ ] Profile system under load

  - Identify bottlenecks
  - Optimize Elasticsearch queries and indexing
  - Optimize event processing and Redis buffering

- [ ] Implement caching strategies

  - Configuration caching
  - Query result caching
  - Static asset caching

- [ ] Optimize resource usage
  - Container resource limits
  - Elasticsearch connection pooling
  - Redis connection pooling
  - Async I/O optimization

#### 9.5 Operational Tooling

- [ ] Create deployment automation

  - Blue-green or canary deployments
  - Automated rollback on failure

- [ ] Create backup and recovery procedures

  - Elasticsearch snapshot and restore
  - Event store backups (snapshot indices)
  - Configuration backups (snapshot indices)
  - Redis persistence configuration (RDB + AOF)
  - Disaster recovery plan
  - Point-in-time recovery using snapshots

- [ ] Create operational documentation
  - Deployment guide
  - Troubleshooting guide
  - Architecture overview
  - API documentation
  - Elasticsearch index management guide
  - Redis buffer monitoring guide
  - **Resilience configuration guide** (NEW):
    - Circuit breaker tuning
    - Rate limiter configuration
    - Retry policy customization
    - Timeout adjustment guidelines
    - Service-specific resilience patterns

### Success Criteria

- [ ] System reliability > 99.5% uptime
- [ ] Comprehensive monitoring and alerting in place
- [ ] Performance meets SLAs
- [ ] Operational tooling complete
- [ ] Documentation complete
- [ ] On-call runbooks ready

### Risks & Mitigations

- **Risk**: Production incidents during initial rollout
  - **Mitigation**: Gradual rollout, enhanced monitoring, on-call team ready
- **Risk**: Performance issues under real load
  - **Mitigation**: Load testing, performance benchmarks, optimization

---

## Parallel Development Tracks

Some components can be developed in parallel to reduce overall timeline:

### Track 1: Core Domain + Event Sourcing

- Phase 1: Foundation & Core Domain
- Phase 3: Event Sourcing Infrastructure (Elasticsearch + Redis)

### Track 2: Ports, Adapters & Infrastructure

- Phase 2: Port Interfaces & Basic Adapters
  - Includes infrastructure resilience layer (circuit breakers, rate limiting, retries, timeouts)
- Phase 4: Mock Adapters & Simulation Mode

### Track 3: Application Layer

- Phase 5: Application Services

### Track 4: API Layer

- Phase 6: Primary Adapters & API Layer

### Track 5: Configuration

- Phase 7: Configuration System

With parallel tracks, timeline can be reduced to approximately 20-28 weeks (5-7 months).

---

## Testing Strategy

### Test Pyramid

```
       ┌──────────────┐
       │  E2E Tests   │ - Simulation scenarios, API tests
       └──────────────┘
      ┌────────────────┐
      │Integration Tests│ - Application services with mock adapters
      └────────────────┘
    ┌────────────────────┐
    │    Unit Tests      │ - Domain models, value objects, adapters
    └────────────────────┘
```

### Test Coverage Targets

- Domain layer: 100%
- Application services: 90%
- Adapters: 80%
- Overall: 85%

### Test Types

1. **Unit Tests**: Fast, isolated, no external dependencies
2. **Integration Tests**: Test component interactions with mock adapters
3. **Simulation Tests**: End-to-end workflows in simulation mode
4. **Contract Tests**: Verify adapters conform to port interfaces
5. **Performance Tests**: Load testing, stress testing
6. **Security Tests**: Authentication, authorization, input validation

---

## Deployment Strategy

### Infrastructure Requirements

- **Compute**: Kubernetes cluster for services, Docker for agent containers
- **Storage**:
  - Elasticsearch cluster (primary persistence: events, logs, configuration, metrics)
  - Redis cluster (buffering and caching: event buffer, config cache, task queue)
- **Monitoring**: Prometheus, Grafana, Kibana, Jaeger/Kibana APM
- **Background Workers**: Worker pool for Redis → Elasticsearch persistence

### Deployment Phases

1. **Development**: Local development with Docker Compose (Elasticsearch + Redis + services)
2. **Staging**: Staging environment with production-like infrastructure
3. **Production Pilot**: Single project on Gen 2
4. **Production Rollout**: Gradual migration of all projects
5. **Full Production**: Gen 1 decommissioned

---

## Success Metrics

### Development Metrics

- Code coverage: > 85%
- Build time: < 5 minutes
- Test execution time: < 10 minutes
- Code review turnaround: < 1 day

### System Metrics

- Uptime: > 99.5%
- Mean time to recovery: < 30 minutes
- Execution success rate: > 95%
- Average execution duration: < target SLA

### Business Metrics

- Work items processed per day: > current baseline
- User satisfaction: > 4/5
- Time to value: < current baseline
- System extensibility: New adapters < 1 week

---

## Risk Management

### High-Priority Risks

1. **Complex domain model** - Mitigate with regular reviews and refactoring
2. **Event sourcing complexity** - Mitigate with comprehensive testing and documentation
3. **Elasticsearch + Redis architecture** - Mitigate with monitoring, alerting, and disaster recovery plans
4. **Adapter compatibility** - Mitigate with contract tests and versioning
5. **Infrastructure resilience configuration** - Mitigate with load testing, observability, and tuning
6. **Migration issues** - Mitigate with phased approach and rollback plan
7. **Performance issues** - Mitigate with load testing and optimization

### Risk Monitoring

- Weekly risk review in team meetings
- Risk register updated continuously
- Escalation path defined

---

## Documentation Requirements

### Technical Documentation

- [ ] Architecture overview (high-level)
- [ ] Domain model documentation
- [ ] API documentation (OpenAPI)
- [ ] Adapter documentation (each adapter)
- [ ] **Infrastructure resilience documentation** (NEW)
  - Circuit breaker patterns
  - Rate limiting strategies
  - Retry policy configuration
  - Timeout management
  - Resilient adapter composition
- [ ] Event catalog
- [ ] Configuration guide (Elasticsearch + Redis architecture)
- [ ] Deployment guide

### Operational Documentation

- [ ] Runbooks for common issues
- [ ] Troubleshooting guide
- [ ] Monitoring and alerting guide
- [ ] Backup and recovery procedures

### User Documentation

- [ ] Getting started guide
- [ ] Configuration management guide
- [ ] API usage guide
- [ ] CLI usage guide

---

## Appendix

### Technology Stack

- **Language**: Python 3.11+
- **Web Framework**: FastAPI
- **Search & Storage**: Elasticsearch (events, logs, configuration, metrics)
- **Caching & Buffering**: Redis (event buffering, config caching, task queues)
- **Container Runtime**: Docker
- **Testing**: pytest, pytest-asyncio, testcontainers (Elasticsearch, Redis)
- **API Documentation**: OpenAPI/Swagger
- **Monitoring**: Prometheus, Grafana, Kibana, Jaeger/Kibana APM
- **Infrastructure Resilience**: Custom implementations (circuit breakers, rate limiters, retry policies, timeouts)
- **Frontend**: React or Vue (for dashboard)

### References

- See `02_high_level_arch.md` for architecture details
- See `01_design_changes.md` for design requirements (includes Elasticsearch + Redis architecture rationale)
- See `infrastructure/resilience_infrastructure_design.md` for resilience layer details
- See `external_systems/elasticsearch_design.md` for Elasticsearch integration
- See `external_systems/redis_design.md` for Redis buffering and caching
- See `output_ports/ievent_store_design.md` for event store architecture
- See `output_ports/iconfig_store_design.md` for configuration storage architecture
- See `domains/`, `ports/`, `adapters/`, `application_services/` for component details
