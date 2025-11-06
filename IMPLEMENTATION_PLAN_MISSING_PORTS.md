# Implementation Plan: Missing Port Implementations

## Overview

This document provides a comprehensive implementation plan for the missing input port adapters identified in PR feedback.

## Status Summary

### ✅ Completed
- Directory structure created: `/workspace/src/codetoreum/adapters/primary/input_port_adapters/`
- Mock Agent Query Adapter: `mock/mock_agent_query_adapter.py`
- Mock Agent Command Adapter: `mock/mock_agent_command_adapter.py`

### 🚧 In Progress
- Remaining mock adapters (7 more)

### ⏳ Pending
- PostgreSQL schema design for read models
- PostgreSQL-backed query adapters (6 adapters)
- Command adapter implementations (2 remaining: Execution, WorkItem)
- Application service creation/updates
- Wire up in `create_app()` and `create_development_app()`
- Integration tests

---

## Architecture Design

### Data Flow

```
┌─────────────────────────────────────────────────────────────────┐
│                         REST API / WebSocket                      │
│                      (FastAPI - Primary Adapter)                  │
└───────────────────────────────┬─────────────────────────────────┘
                                │
                                ▼
                    ┌───────────────────────┐
                    │   Input Port Interface │
                    │   (IAgentQueryPort,    │
                    │    IAgentCommandPort)  │
                    └───────────┬───────────┘
                                │
                    ┌───────────┴───────────┐
                    │                       │
                    ▼                       ▼
        ┌──────────────────────┐  ┌──────────────────────┐
        │  Query Adapter        │  │  Command Adapter      │
        │  (PostgreSQL)         │  │  (App Service)        │
        └──────────┬───────────┘  └──────────┬───────────┘
                   │                          │
                   │                          ▼
                   │              ┌──────────────────────┐
                   │              │ Application Service   │
                   │              │ (Business Logic)      │
                   │              └──────────┬───────────┘
                   │                         │
                   │                         ▼
                   │              ┌──────────────────────┐
                   │              │  Domain Aggregate     │
                   │              │  (Agent, WorkItem)    │
                   │              └──────────┬───────────┘
                   │                         │
                   │                         ▼
                   │              ┌──────────────────────┐
                   │              │   Event Store         │
                   │              │   (Events Persisted)  │
                   │              └──────────┬───────────┘
                   │                         │
                   │ ◄───────────────────────┘
                   │   (Event projection to read model)
                   ▼
        ┌──────────────────────┐
        │   PostgreSQL          │
        │   (Read Models)       │
        └──────────────────────┘
```

### Storage Strategy

**Query Ports (Read Operations):**
- Backed by PostgreSQL read models
- Fast queries with filtering, sorting, pagination, full-text search
- Read models are projections built from domain events
- Eventually consistent with write side

**Command Ports (Write Operations):**
- Delegate to Application Services
- Load aggregates from Event Store
- Execute business logic in domain models
- Emit domain events
- Persist events to Event Store
- Trigger read model projections

---

## Implementation Details

### 1. Mock Adapters (For Testing/Development)

#### Completed
✅ **MockAgentQueryAdapter** - `/workspace/src/codetoreum/adapters/primary/input_port_adapters/mock/mock_agent_query_adapter.py`
- In-memory storage using `Dict[str, AgentInfo]`
- Thread-safe with RLock
- Full filtering, sorting, pagination support
- Capability-based queries
- Helper method: `add_agent(agent, stats)` for test data

✅ **MockAgentCommandAdapter** - `/workspace/src/codetoreum/adapters/primary/input_port_adapters/mock/mock_agent_command_adapter.py`
- In-memory storage using `Dict[str, Agent]`
- Thread-safe with RLock
- Full CRUD operations
- Capability and MCP server management
- Helper method: `get_agent(agent_id)` for testing

#### To Implement

**MockExecutionQueryAdapter**
- File: `mock/mock_execution_query_adapter.py`
- Storage: `Dict[str, ExecutionInfo]`
- Features:
  - List executions with filters (status, agent_id, work_item_id, workflow_id, stage_name, date range)
  - Get execution with error details
  - Get execution logs (with stage filter and tail)
  - Get execution history (event timeline)
  - Count executions
- Helper methods:
  - `add_execution(execution_info)`
  - `add_log_entry(execution_id, log_entry)`
  - `add_history_event(execution_id, event)`

**MockExecutionCommandAdapter**
- File: `mock/mock_execution_command_adapter.py`
- Storage: `Dict[str, AgentExecution]` (domain model)
- Features:
  - Terminate execution (stop container, cleanup, emit event)
  - Pause execution (if supported by LLM provider)
  - Resume execution (restore state, resume container)
- Helper methods:
  - `add_execution(execution)`
  - `get_execution(execution_id)`

**MockWorkItemQueryAdapter**
- File: `mock/mock_work_item_query_adapter.py`
- Storage: `Dict[str, WorkItem]`
- Features:
  - Get work item by ID
  - List work items (filters: project_id, status, assignee, labels, workflow_stage, priority, date ranges)
  - Search work items (full-text search in title/description)
  - Get work item history (events)
  - Count work items
- Helper methods:
  - `add_work_item(work_item)`
  - `add_event(work_item_id, event)`

**MockWorkItemCommandAdapter**
- File: `mock/mock_work_item_command_adapter.py`
- Storage: `Dict[str, WorkItem]`
- Features:
  - Create work item
  - Update work item (title, description, labels, priority)
  - Delete work item (soft delete)
  - Assign agent
  - Update labels
  - Update priority
  - Attach workflow
  - Update stage
- Helper methods:
  - `get_work_item(work_item_id)`

**MockMetricsQueryAdapter**
- File: `mock/mock_metrics_query_adapter.py`
- Storage: In-memory time series data structures
- Features:
  - Get system health (all components)
  - Get component health (specific component)
  - Get performance metrics (API, execution, resources, queue)
  - Get resilience metrics (circuit breakers, rate limiters, retries, timeouts)
  - Get integration status (GitHub, Docker, Event Store, Config Store)
  - Get simulation mode info
  - Get metric time series (with aggregation)
  - List metric names
  - Get API endpoint metrics
  - Get agent execution metrics
- Helper methods:
  - `set_component_health(component_name, health_info)`
  - `record_metric(metric_name, value, timestamp, labels)`
  - `set_integration_status(status)`

**MockConfigQueryAdapter**
- File: `mock/mock_config_query_adapter.py`
- Storage:
  - `Dict[str, ProjectConfigInfo]`
  - `Dict[str, AgentConfigInfo]`
  - `Dict[str, PipelineConfigInfo]`
  - `Dict[str, List[ConfigVersionInfo]]` (version history)
- Features:
  - Get project config (by ID or name)
  - Get agent config
  - Get pipeline config
  - List projects/agents/pipelines
  - Search configs (full-text)
  - Get config version history
  - Get specific config version
  - Count configs
- Helper methods:
  - `add_project_config(config)`
  - `add_agent_config(config)`
  - `add_pipeline_config(config)`
  - `add_config_version(config_id, version_info)`

**MockWorkspaceQueryAdapter**
- File: `mock/mock_workspace_query_adapter.py`
- Storage: `Dict[str, WorkspaceInfo]`
- Features:
  - Get workspace (by workspace_id or execution_id)
  - List workspaces (with filters: execution_id, agent_id, work_item_id, project_id, status)
  - List active workspaces
  - Get resource usage summary
  - Count workspaces
  - Get workspace logs (with tail and since filters)
- Helper methods:
  - `add_workspace(workspace_info)`
  - `update_resource_usage(workspace_id, usage)`
  - `add_log_line(workspace_id, log_line)`

---

### 2. PostgreSQL Schema for Read Models

**Tables to Create:**

```sql
-- Agent read model
CREATE TABLE agent_read_model (
    id UUID PRIMARY KEY,
    name VARCHAR(255) UNIQUE NOT NULL,
    display_name VARCHAR(255) NOT NULL,
    agent_type VARCHAR(50) NOT NULL,
    role_description TEXT NOT NULL,
    model VARCHAR(100) NOT NULL,
    timeout_seconds INTEGER NOT NULL,
    max_retries INTEGER NOT NULL,
    requires_docker BOOLEAN NOT NULL,
    requires_dev_container BOOLEAN NOT NULL,
    makes_code_changes BOOLEAN NOT NULL,
    filesystem_write_allowed BOOLEAN NOT NULL,
    mcp_servers JSONB NOT NULL DEFAULT '[]',
    capabilities JSONB NOT NULL DEFAULT '{}',
    environment_variables JSONB,
    metadata JSONB NOT NULL DEFAULT '{}',
    created_at TIMESTAMP WITH TIME ZONE NOT NULL,
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL,
    version INTEGER NOT NULL DEFAULT 0
);

CREATE INDEX idx_agent_name ON agent_read_model(name);
CREATE INDEX idx_agent_type ON agent_read_model(agent_type);
CREATE INDEX idx_agent_capabilities ON agent_read_model USING GIN(capabilities);
CREATE INDEX idx_agent_updated_at ON agent_read_model(updated_at DESC);

-- Agent execution stats (separate table, updated periodically)
CREATE TABLE agent_execution_stats (
    agent_id UUID PRIMARY KEY REFERENCES agent_read_model(id) ON DELETE CASCADE,
    total_executions INTEGER NOT NULL DEFAULT 0,
    successful_executions INTEGER NOT NULL DEFAULT 0,
    failed_executions INTEGER NOT NULL DEFAULT 0,
    timeout_executions INTEGER NOT NULL DEFAULT 0,
    average_duration_seconds REAL,
    last_execution_at TIMESTAMP WITH TIME ZONE,
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL
);

-- Execution read model
CREATE TABLE execution_read_model (
    id UUID PRIMARY KEY,
    agent_id UUID NOT NULL,
    agent_name VARCHAR(255) NOT NULL,
    work_item_id UUID NOT NULL,
    workflow_id UUID NOT NULL,
    stage_name VARCHAR(255) NOT NULL,
    status VARCHAR(50) NOT NULL,
    container_name VARCHAR(255),
    container_id VARCHAR(255),
    output TEXT,
    error_message TEXT,
    error_type VARCHAR(50),
    error_details JSONB,
    exit_code INTEGER,
    input_tokens INTEGER NOT NULL DEFAULT 0,
    output_tokens INTEGER NOT NULL DEFAULT 0,
    duration_seconds REAL,
    initialized_at TIMESTAMP WITH TIME ZONE NOT NULL,
    started_at TIMESTAMP WITH TIME ZONE,
    completed_at TIMESTAMP WITH TIME ZONE,
    version INTEGER NOT NULL DEFAULT 0
);

CREATE INDEX idx_execution_agent ON execution_read_model(agent_id);
CREATE INDEX idx_execution_work_item ON execution_read_model(work_item_id);
CREATE INDEX idx_execution_workflow ON execution_read_model(workflow_id);
CREATE INDEX idx_execution_status ON execution_read_model(status);
CREATE INDEX idx_execution_initialized_at ON execution_read_model(initialized_at DESC);

-- Execution logs
CREATE TABLE execution_logs (
    id BIGSERIAL PRIMARY KEY,
    execution_id UUID NOT NULL,
    timestamp TIMESTAMP WITH TIME ZONE NOT NULL,
    level VARCHAR(20) NOT NULL,
    message TEXT NOT NULL,
    stage VARCHAR(255)
);

CREATE INDEX idx_execution_logs_execution ON execution_logs(execution_id, timestamp DESC);

-- Work item read model
CREATE TABLE work_item_read_model (
    id UUID PRIMARY KEY,
    project_id UUID NOT NULL,
    title VARCHAR(500) NOT NULL,
    description TEXT NOT NULL,
    status VARCHAR(50) NOT NULL,
    priority VARCHAR(20) NOT NULL,
    assignee UUID,
    labels JSONB NOT NULL DEFAULT '[]',
    workflow_id UUID,
    workflow_stage VARCHAR(255),
    external_id VARCHAR(255),
    external_url VARCHAR(500),
    metadata JSONB NOT NULL DEFAULT '{}',
    created_at TIMESTAMP WITH TIME ZONE NOT NULL,
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL,
    version INTEGER NOT NULL DEFAULT 0
);

CREATE INDEX idx_work_item_project ON work_item_read_model(project_id);
CREATE INDEX idx_work_item_status ON work_item_read_model(status);
CREATE INDEX idx_work_item_assignee ON work_item_read_model(assignee);
CREATE INDEX idx_work_item_labels ON work_item_read_model USING GIN(labels);
CREATE INDEX idx_work_item_workflow ON work_item_read_model(workflow_id);
CREATE INDEX idx_work_item_external_id ON work_item_read_model(external_id);
CREATE INDEX idx_work_item_updated_at ON work_item_read_model(updated_at DESC);
CREATE INDEX idx_work_item_search ON work_item_read_model USING GIN(to_tsvector('english', title || ' ' || description));

-- Configuration read models
CREATE TABLE project_config_read_model (
    id UUID PRIMARY KEY,
    name VARCHAR(255) UNIQUE NOT NULL,
    description TEXT,
    github_org VARCHAR(255),
    github_repo VARCHAR(255),
    environment_variables JSONB NOT NULL DEFAULT '{}',
    mounted_commands JSONB NOT NULL DEFAULT '[]',
    mounted_subagents JSONB NOT NULL DEFAULT '[]',
    metadata JSONB NOT NULL DEFAULT '{}',
    version INTEGER NOT NULL DEFAULT 0,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL,
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL
);

CREATE INDEX idx_project_config_name ON project_config_read_model(name);

-- Workspace read model
CREATE TABLE workspace_read_model (
    id UUID PRIMARY KEY,
    execution_id UUID UNIQUE NOT NULL,
    agent_id UUID NOT NULL,
    agent_name VARCHAR(255) NOT NULL,
    work_item_id UUID NOT NULL,
    project_id UUID NOT NULL,
    container_id VARCHAR(255),
    container_name VARCHAR(255),
    image_name VARCHAR(255) NOT NULL,
    status VARCHAR(50) NOT NULL,
    context_path VARCHAR(500) NOT NULL,
    artifacts_path VARCHAR(500),
    working_directory VARCHAR(500) NOT NULL,
    mounted_files JSONB NOT NULL DEFAULT '[]',
    environment_variables JSONB NOT NULL DEFAULT '{}',
    metadata JSONB NOT NULL DEFAULT '{}',
    cpu_percent REAL,
    memory_mb REAL,
    memory_limit_mb REAL,
    disk_usage_mb REAL,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL,
    started_at TIMESTAMP WITH TIME ZONE,
    stopped_at TIMESTAMP WITH TIME ZONE,
    last_activity TIMESTAMP WITH TIME ZONE,
    version INTEGER NOT NULL DEFAULT 0
);

CREATE INDEX idx_workspace_execution ON workspace_read_model(execution_id);
CREATE INDEX idx_workspace_agent ON workspace_read_model(agent_id);
CREATE INDEX idx_workspace_work_item ON workspace_read_model(work_item_id);
CREATE INDEX idx_workspace_project ON workspace_read_model(project_id);
CREATE INDEX idx_workspace_status ON workspace_read_model(status);
CREATE INDEX idx_workspace_last_activity ON workspace_read_model(last_activity DESC);

-- Metrics time series (simplified - for POC, use Prometheus for production)
CREATE TABLE metrics_time_series (
    id BIGSERIAL PRIMARY KEY,
    metric_name VARCHAR(255) NOT NULL,
    timestamp TIMESTAMP WITH TIME ZONE NOT NULL,
    value REAL NOT NULL,
    labels JSONB NOT NULL DEFAULT '{}'
);

CREATE INDEX idx_metrics_name_time ON metrics_time_series(metric_name, timestamp DESC);
CREATE INDEX idx_metrics_labels ON metrics_time_series USING GIN(labels);
```

---

### 3. PostgreSQL-Backed Query Adapters

**File Structure:**
```
src/codetoreum/adapters/primary/input_port_adapters/query/
├── __init__.py
├── postgres_agent_query_adapter.py
├── postgres_execution_query_adapter.py
├── postgres_work_item_query_adapter.py
├── postgres_metrics_query_adapter.py
├── postgres_config_query_adapter.py
└── postgres_workspace_query_adapter.py
```

**Common Pattern:**
```python
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_, or_

class PostgresAgentQueryAdapter(IAgentQueryPort):
    def __init__(self, session_factory):
        self._session_factory = session_factory

    async def get_agent(self, agent_id: str, include_stats: bool = False) -> AgentInfo:
        async with self._session_factory() as session:
            # Query agent_read_model table
            # Join with agent_execution_stats if include_stats=True
            # Convert row to AgentInfo
            pass
```

---

### 4. Command Adapter Implementations

**Pattern:**
```python
class AgentCommandAdapter(IAgentCommandPort):
    def __init__(
        self,
        agent_service: AgentService,  # Application service
        event_bus: IEventBus
    ):
        self._agent_service = agent_service
        self._event_bus = event_bus

    async def create_agent(self, command: CreateAgentCommand) -> Agent:
        # Delegate to application service
        agent = await self._agent_service.create_agent(
            name=command.name,
            display_name=command.display_name,
            # ... other fields
        )

        # Publish domain events
        for event in agent._events:
            await self._event_bus.publish(event)

        return agent
```

---

### 5. Application Services (If Missing)

**AgentService** (likely already exists)
- Create agent
- Update agent
- Add/remove/update capabilities
- Add/remove MCP servers
- Delete agent

**ExecutionService** (likely already exists)
- Start execution
- Terminate execution
- Pause execution
- Resume execution

**WorkItemService** (may need to be created)
- Create work item
- Update work item
- Delete work item
- Assign agent
- Update labels/priority
- Attach workflow
- Update stage

---

### 6. Wire Up in FastAPI App

**Update `create_app()` in `/workspace/src/codetoreum/adapters/primary/fastapi_app.py`:**

```python
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker

from codetoreum.adapters.primary.input_port_adapters.query import (
    PostgresAgentQueryAdapter,
    PostgresExecutionQueryAdapter,
    # ... other query adapters
)

from codetoreum.adapters.primary.input_port_adapters.command import (
    AgentCommandAdapter,
    ExecutionCommandAdapter,
    WorkItemCommandAdapter,
)

def create_app(
    # Database
    database_url: str,
    # Event store
    event_store: IEventStore,
    # Application services
    agent_service: AgentService,
    execution_service: ExecutionService,
    work_item_service: WorkItemService,
    # ... other dependencies
) -> FastAPI:
    # Create database session factory
    engine = create_async_engine(database_url, echo=False)
    session_factory = sessionmaker(
        engine,
        class_=AsyncSession,
        expire_on_commit=False
    )

    # Create query adapters
    agent_query_port = PostgresAgentQueryAdapter(session_factory)
    execution_query_port = PostgresExecutionQueryAdapter(session_factory, event_store)
    work_item_query_port = PostgresWorkItemQueryAdapter(session_factory, event_store)
    metrics_query_port = PostgresMetricsQueryAdapter(session_factory)
    config_query_port = PostgresConfigQueryAdapter(session_factory)
    workspace_query_port = PostgresWorkspaceQueryAdapter(session_factory)

    # Create command adapters
    agent_command_port = AgentCommandAdapter(agent_service, event_bus)
    execution_command_port = ExecutionCommandAdapter(execution_service, event_bus)
    work_item_command_port = WorkItemCommandAdapter(work_item_service, event_bus)

    # Create FastAPI app
    app = FastAPI(...)

    # Register routers with port dependencies
    app.include_router(
        agent_router,
        dependencies=[
            Depends(lambda: agent_query_port),
            Depends(lambda: agent_command_port),
        ]
    )

    # ... register other routers

    return app
```

**Update `create_development_app()`:**

```python
def create_development_app() -> FastAPI:
    # Use mock adapters for development
    from codetoreum.adapters.primary.input_port_adapters.mock import (
        MockAgentQueryAdapter,
        MockAgentCommandAdapter,
        # ... other mock adapters
    )

    # Create mock instances
    agent_query_port = MockAgentQueryAdapter()
    agent_command_port = MockAgentCommandAdapter()
    # ... other mock adapters

    # Seed with test data
    from codetoreum.domain.agent import Agent, AgentType, AgentCapability
    test_agent = Agent(...)
    agent_query_port.add_agent(test_agent)
    agent_command_port._agents[test_agent.id] = test_agent

    # Create app
    app = FastAPI(...)
    # ... rest of setup

    return app
```

---

## Estimated Effort

| Task | Estimated Time | Priority |
|------|----------------|----------|
| Complete 7 remaining mock adapters | 4-6 hours | P0 |
| Design & create PostgreSQL schema | 2-3 hours | P0 |
| Implement 6 PostgreSQL query adapters | 8-10 hours | P0 |
| Implement 2 remaining command adapters | 2-3 hours | P1 |
| Create/update application services | 4-6 hours | P1 |
| Wire up in create_app() | 2-3 hours | P0 |
| Wire up in create_development_app() | 1-2 hours | P0 |
| Write integration tests | 6-8 hours | P0 |
| Documentation updates | 2-3 hours | P2 |
| **Total** | **31-44 hours** | **~4-6 days** |

---

## Testing Strategy

### Unit Tests
- Test each mock adapter in isolation
- Test filtering, sorting, pagination logic
- Test error handling (not found, validation errors)

### Integration Tests
- Test PostgreSQL query adapters with real database (testcontainers)
- Test command adapters with application services
- Test end-to-end: API → Command Adapter → App Service → Event Store → Query Adapter

### Contract Tests
- Verify all adapters implement port interfaces correctly
- Verify mock and production adapters have same behavior (within reasonable bounds)

---

## Next Steps

1. **Complete mock adapters** (7 remaining) - These are critical for `create_development_app()`
2. **Design PostgreSQL schema** - Review with team before implementing
3. **Implement PostgreSQL query adapters** - Can be parallelized
4. **Implement command adapters** - Depends on application services being ready
5. **Wire up in app factories** - Integration point
6. **Write tests** - Validate all implementations
7. **Update documentation** - Architecture diagrams, API docs

---

## Questions & Decisions Needed

1. **Database Selection**: Confirm PostgreSQL is the choice for read models
2. **Event Store**: Confirm ElasticsearchEventStore is ready and supports required queries
3. **Application Services**: Do ExecutionService and WorkItemService exist? Need creation?
4. **Metrics Storage**: Use PostgreSQL for POC, or integrate Prometheus immediately?
5. **Full-Text Search**: Use PostgreSQL `tsvector`, or integrate Elasticsearch?
6. **Config Storage**: Reuse `ElasticsearchConfigStorage` adapter, or create PostgreSQL version?

---

## References

- **Port Interfaces**: `/workspace/src/codetoreum/ports/input/`
- **Domain Models**: `/workspace/src/codetoreum/domain/`
- **Existing Secondary Adapters**: `/workspace/src/codetoreum/adapters/secondary/`
- **FastAPI App Factory**: `/workspace/src/codetoreum/adapters/primary/fastapi_app.py`
- **Design Documentation**: `/workspace/documentation/01_design/`
