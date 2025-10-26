# Implementation Plan: Codetoreum Generation 2

## Overview

This document provides a detailed, phased implementation plan for building Codetoreum Generation 2 based on the Hexagonal Architecture with Event Sourcing described in `02_high_level_arch.md`. The plan prioritizes testability, simulation capabilities, and incremental delivery.

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

#### 2.3 Production Secondary Adapters

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

#### 2.4 Testing Adapters

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

#### 2.5 Adapter Registry & Factory

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
- [ ] Critical production adapters implemented and tested
- [ ] In-memory/mock adapters available for all ports
- [ ] Adapter registry and factory working
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
- Create event streaming capabilities
- Build event replay and debugging tools

### Deliverables

#### 3.1 Event Store Implementation

**See `external_systems/redis_design.md` and `output_ports/event_store_port.md`**

- [ ] Implement `RedisEventStore` (Production)

  - Redis Streams for event storage
  - Support for event versioning
  - Efficient querying by aggregate ID, timestamp, event type
  - Optimistic concurrency control
  - Integration tests with Redis testcontainer

- [ ] Implement `PostgreSQLEventStore` (Alternative)

  - Table design: events(id, aggregate_id, event_type, data, timestamp, version)
  - Indexed queries for replay
  - Transaction support
  - Integration tests with PostgreSQL testcontainer

- [ ] Implement event serialization
  - JSON serialization with schema versioning
  - Support for backward/forward compatibility
  - Compression for large events

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

- Replace YAML files with database-backed configuration
- Build web UI for configuration management
- Implement configuration versioning and rollback
- Support project-specific and global configurations

### Deliverables

#### 7.1 Configuration Database Schema

- [ ] Design database schema

  - projects table
  - workflows table
  - workflow_stages table
  - agents table
  - agent_configurations table
  - environment_variables table
  - configuration_history table

- [ ] Implement database migrations (Alembic)

  - Initial schema
  - Support for schema evolution

- [ ] Create ORM models (SQLAlchemy or similar)

#### 7.2 Configuration Storage Adapter

- [ ] Implement `PostgreSQLConfigStorage`

  - CRUD operations for all configuration entities
  - Query methods for complex lookups
  - Transaction support
  - Integration tests with test database

- [ ] Implement configuration caching
  - Redis-backed cache
  - Cache invalidation on updates
  - TTL-based expiration

#### 7.3 Configuration Service Enhancement

- [ ] Enhance `ConfigurationService`

  - Database-backed storage
  - Configuration validation
  - Configuration versioning
  - Audit trail for changes
  - Rollback capability

- [ ] Implement configuration templates
  - Pre-built workflow templates
  - Pre-configured agent types
  - Easy instantiation for new projects

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
  - Import into database
  - Generate migration report

- [ ] Test migration with existing configurations

  - Verify all data migrated correctly
  - Validate behavior unchanged

- [ ] Documentation for configuration management

### Success Criteria

- [ ] Database schema designed and implemented
- [ ] Configuration stored in database, not YAML files
- [ ] Web UI for configuration management working
- [ ] Configuration versioning and rollback working
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

  - Import configuration to Gen 2 database
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

- [ ] Implement circuit breakers

  - For external API calls
  - For database connections
  - For event store operations

- [ ] Implement retry logic with backoff

  - Exponential backoff for transient failures
  - Configurable retry limits
  - Dead letter queue for failed events

- [ ] Implement rate limiting

  - API rate limits
  - LLM provider rate limits
  - GitHub API rate limits

- [ ] Implement health checks
  - Liveness probe
  - Readiness probe
  - Dependency health checks

#### 9.2 Monitoring & Observability

- [ ] Implement structured logging

  - Contextual logging with trace IDs
  - Log levels appropriate for production
  - Sensitive data redaction

- [ ] Implement metrics collection

  - Execution metrics (duration, success rate, etc.)
  - System metrics (CPU, memory, etc.)
  - Business metrics (workflows completed, work items processed, etc.)
  - Integration with Prometheus/Grafana

- [ ] Implement distributed tracing

  - OpenTelemetry integration
  - Trace execution flow across services
  - Integration with Jaeger or similar

- [ ] Create monitoring dashboards
  - System health dashboard
  - Execution metrics dashboard
  - Business metrics dashboard

#### 9.3 Alerting

- [ ] Define alert conditions

  - Execution failures above threshold
  - System errors above threshold
  - Performance degradation
  - Dependency failures

- [ ] Implement alerting

  - Integration with PagerDuty or similar
  - Alert routing based on severity
  - Alert aggregation to reduce noise

- [ ] Create runbooks for alerts
  - Troubleshooting steps
  - Resolution procedures
  - Escalation paths

#### 9.4 Performance Optimization

- [ ] Profile system under load

  - Identify bottlenecks
  - Optimize database queries
  - Optimize event processing

- [ ] Implement caching strategies

  - Configuration caching
  - Query result caching
  - Static asset caching

- [ ] Optimize resource usage
  - Container resource limits
  - Database connection pooling
  - Async I/O optimization

#### 9.5 Operational Tooling

- [ ] Create deployment automation

  - Blue-green or canary deployments
  - Automated rollback on failure

- [ ] Create backup and recovery procedures

  - Database backups
  - Event store backups
  - Configuration backups
  - Disaster recovery plan

- [ ] Create operational documentation
  - Deployment guide
  - Troubleshooting guide
  - Architecture overview
  - API documentation

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
- Phase 3: Event Sourcing Infrastructure

### Track 2: Ports & Adapters

- Phase 2: Port Interfaces & Basic Adapters
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
- **Storage**: PostgreSQL for configuration, Redis for event store, S3 for artifacts
- **Monitoring**: Prometheus, Grafana, Jaeger

### Deployment Phases

1. **Development**: Local development with Docker Compose
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
3. **Adapter compatibility** - Mitigate with contract tests and versioning
4. **Migration issues** - Mitigate with phased approach and rollback plan
5. **Performance issues** - Mitigate with load testing and optimization

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
- [ ] Event catalog
- [ ] Configuration guide
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
- **ORM**: SQLAlchemy
- **Database**: PostgreSQL (config), Redis (events)
- **Container Runtime**: Docker
- **Testing**: pytest, pytest-asyncio, testcontainers
- **API Documentation**: OpenAPI/Swagger
- **Monitoring**: Prometheus, Grafana, Jaeger
- **Frontend**: React or Vue (for dashboard)

### References

- See `02_high_level_arch.md` for architecture details
- See `01_design_changes.md` for design requirements
- See `domains/`, `ports/`, `adapters/`, `application_services/` for component details
