# Phase 6: REST API Implementation - Current State Overview

## Executive Summary

This document provides a comprehensive overview of the current REST API implementation in Codetoreum, including:
- Existing routers and endpoints
- Port interfaces for configuration, metrics, and workspace management
- Data Transfer Objects (DTOs) for requests/responses
- Authentication and dependency injection setup
- FastAPI application structure and router registration

**Current State**: The REST API is well-structured with multiple routers in place, following the hexagonal architecture pattern. Most core functionality routers exist, but Phase 6 appears to need configuration management, metrics, and workspace management endpoints.

---

## 1. Existing Routers

### 1.1 Router Registration

Location: `/workspace/src/codetoreum/adapters/primary/fastapi_app.py` (lines 325-372)

All routers are registered in the `create_app()` function:

```python
# Include REST API router
app.include_router(rest_api_adapter.router)

# Include Work Items router
work_items_router = create_work_items_router(...)
app.include_router(work_items_router)

# Include Workflows router
workflows_router = create_workflows_router(...)
app.include_router(workflows_router)

# Include Orchestrator router
orchestrator_router = create_orchestrator_router(...)
app.include_router(orchestrator_router)

# Include Scheduler router
scheduler_router = create_scheduler_router(...)
app.include_router(scheduler_router)

# Include Agents router
agents_router = create_agents_router(...)
app.include_router(agents_router)

# Include Executions router
executions_router = create_executions_router(...)
app.include_router(executions_router)
```

### 1.2 Existing Router Summary

| Router | Location | Prefix | Key Endpoints | Status |
|--------|----------|--------|---------------|--------|
| **Work Items** | `routers/work_items.py` | `/api/v2/work-items` | POST, GET, PUT, DELETE work items; list, search | Implemented |
| **Workflows** | `routers/workflows.py` | `/api/v2/workflows` | Create, read, update, delete workflow definitions; versioning | Implemented |
| **Orchestrator** | `routers/orchestrator.py` | `/api/v2/orchestrator` | Start, pause, resume, cancel executions; entry condition validation | Implemented |
| **Agents** | `routers/agents.py` | `/api/v2/agents` | List agents; capabilities management; MCP servers | Implemented |
| **Executions** | `routers/executions.py` | `/api/v2/executions` | List executions, get status, logs, history; termination | Implemented |
| **Scheduler** | `routers/scheduler.py` | `/api/v2/scheduler` | Task queuing and scheduling operations | Implemented |
| **Events** | `routers/events.py` | (WebSocket) | Real-time event streaming | Implemented |
| **REST API Adapter** | `rest_api_adapter.py` | `/api/v1` | Workflow control, task queries, configuration management | Legacy |

### 1.3 Core Router Details

#### Work Items Router (`/api/v2/work-items`)
**File**: `/workspace/src/codetoreum/adapters/primary/routers/work_items.py`

Endpoints:
- `POST /` - Create work item
- `GET /` - List work items with filtering, pagination, sorting
- `GET /{id}` - Get specific work item
- `PUT /{id}` - Update work item
- `DELETE /{id}` - Delete work item
- `GET /{id}/history` - Get work item history

Dependencies: 
- `IWorkItemCommandPort` - Create/update/delete operations
- `IWorkItemQueryPort` - Read operations

#### Workflows Router (`/api/v2/workflows`)
**File**: `/workspace/src/codetoreum/adapters/primary/routers/workflows.py`

Endpoints:
- `POST /` - Create workflow definition
- `GET /` - List workflows with filters
- `GET /{id}` - Get specific workflow
- `PUT /{id}` - Update workflow
- `DELETE /{id}` - Delete workflow
- `GET /{id}/versions` - Get version history
- `POST /{id}/validate` - Validate workflow
- `POST /{id}/activate` - Activate workflow
- `POST /{id}/deactivate` - Deactivate workflow

Dependencies:
- `IWorkflowDefinitionCommandPort` - Create/update/delete operations
- `IWorkflowQueryPort` - Read operations and validation

#### Orchestrator Router (`/api/v2/orchestrator`)
**File**: `/workspace/src/codetoreum/adapters/primary/routers/orchestrator.py`

Endpoints:
- `POST /start` - Start workflow execution
- `POST /{run_id}/pause` - Pause execution
- `POST /{run_id}/resume` - Resume execution
- `POST /{run_id}/cancel` - Cancel execution
- `POST /check-entry-conditions` - Validate entry conditions

Dependencies:
- `IOrchestrationCommandPort` - Execution commands

#### Agents Router (`/api/v2/agents`)
**File**: `/workspace/src/codetoreum/adapters/primary/routers/agents.py`

Endpoints:
- `GET /` - List agents with filtering
- `POST /` - Create agent
- `GET /{id}` - Get agent details
- `PUT /{id}` - Update agent
- `DELETE /{id}` - Delete agent
- `POST /{id}/capabilities` - Add capability
- `PUT /{id}/capabilities/{skill}` - Update capability
- `DELETE /{id}/capabilities/{skill}` - Remove capability
- `POST /{id}/mcp-servers` - Add MCP server
- `DELETE /{id}/mcp-servers/{name}` - Remove MCP server

Dependencies:
- `IAgentCommandPort` - Create/update/delete operations
- `IAgentQueryPort` - Read operations

#### Executions Router (`/api/v2/executions`)
**File**: `/workspace/src/codetoreum/adapters/primary/routers/executions.py`

Endpoints:
- `GET /` - List executions with filtering
- `GET /{id}` - Get execution status
- `GET /{id}/logs` - Get execution logs
- `GET /{id}/history` - Get execution history
- `POST /{id}/terminate` - Terminate execution
- `POST /{id}/pause` - Pause execution
- `POST /{id}/resume` - Resume execution

Dependencies:
- `IExecutionCommandPort` - Execution control
- `IExecutionQueryPort` - Execution queries

---

## 2. Port Interfaces

### 2.1 Input Ports (Command & Query)

Location: `/workspace/src/codetoreum/ports/input/`

#### Configuration Command Port
**File**: `config_command.py`

```python
class IConfigurationCommandPort(ABC):
    """Input port for configuration commands"""
    
    @abstractmethod
    async def update_project_config(self, command: UpdateProjectConfigCommand) -> ConfigurationCommandResult:
        pass
    
    @abstractmethod
    async def update_agent_config(self, command: UpdateAgentConfigCommand) -> ConfigurationCommandResult:
        pass
    
    @abstractmethod
    async def update_pipeline_config(self, command: UpdatePipelineConfigCommand) -> ConfigurationCommandResult:
        pass
    
    @abstractmethod
    async def add_environment_variable(self, command: AddEnvironmentVariableCommand) -> ConfigurationCommandResult:
        pass
    
    @abstractmethod
    async def remove_environment_variable(self, command: RemoveEnvironmentVariableCommand) -> ConfigurationCommandResult:
        pass
    
    @abstractmethod
    async def mount_command(self, command: MountCommandCommand) -> ConfigurationCommandResult:
        pass
    
    @abstractmethod
    async def unmount_command(self, command: UnmountCommandCommand) -> ConfigurationCommandResult:
        pass
    
    @abstractmethod
    async def mount_subagent(self, command: MountSubAgentCommand) -> ConfigurationCommandResult:
        pass
    
    @abstractmethod
    async def unmount_subagent(self, command: UnmountSubAgentCommand) -> ConfigurationCommandResult:
        pass
```

**Related Commands**:
- `UpdateProjectConfigCommand` - Update project-level settings
- `UpdateAgentConfigCommand` - Update agent configuration
- `UpdatePipelineConfigCommand` - Update pipeline configuration
- `AddEnvironmentVariableCommand` - Add project environment variable
- `RemoveEnvironmentVariableCommand` - Remove environment variable
- `MountCommandCommand` - Mount custom command
- `UnmountCommandCommand` - Unmount custom command
- `MountSubAgentCommand` - Mount sub-agent
- `UnmountSubAgentCommand` - Unmount sub-agent

#### Work Item Ports
**Files**: `work_item_command.py`, `work_item_query.py`

Command Port:
- `create_work_item()`
- `update_work_item()`
- `delete_work_item()`
- `assign_agent()`
- `update_labels()`
- `update_priority()`
- `attach_workflow()`
- `update_stage()`

Query Port:
- `get_work_item()`
- `list_work_items()`
- `search_work_items()`
- `get_work_item_history()`
- `count_work_items()`

#### Workflow Ports
**Files**: `workflow_definition_command.py`, `workflow_query.py`

Command Port:
- `create_workflow_definition()`
- `update_workflow_definition()`
- `delete_workflow_definition()`
- `activate_workflow_definition()`
- `deactivate_workflow_definition()`

Query Port:
- `get_workflow()`
- `list_workflows()`
- `get_workflow_versions()`
- `validate_workflow()`
- `get_workflows_for_work_item_type()`
- `count_active_executions()`

#### Agent Ports
**Files**: `agent_command.py`, `agent_query.py`

Command Port:
- `create_agent()`
- `update_agent()`
- `add_capability()`
- `remove_capability()`
- `update_capability()`
- `add_mcp_server()`
- `remove_mcp_server()`
- `delete_agent()`

Query Port:
- `get_agent()`
- `get_agent_by_name()`
- `list_agents()`
- `list_agents_by_capability()`
- `count_agents()`

#### Execution Ports
**Files**: `execution_command.py`, `execution_query.py`

Command Port:
- `terminate_execution()`
- `pause_execution()`
- `resume_execution()`

Query Port:
- `get_execution()`
- `list_executions()`
- `get_execution_logs()`
- `get_execution_history()`
- `count_executions()`

#### Orchestration Command Port
**File**: `orchestration_command.py`

- `start_execution()`
- `cancel_execution()`
- `pause_execution()`
- `resume_execution()`
- `check_entry_conditions()`

### 2.2 Output Ports (Infrastructure)

Location: `/workspace/src/codetoreum/ports/output/`

#### Metrics Port
**File**: `metrics.py`

```python
class IMetrics(ABC):
    """Interface for metrics collection"""
    
    async def increment_counter(name: str, value: int, labels: Dict[str, str])
    async def set_gauge(name: str, value: float, labels: Dict[str, str])
    async def record_histogram(name: str, value: float, labels: Dict[str, str])
    async def record_summary(name: str, value: float, labels: Dict[str, str])
    async def start_timer(name: str) -> str
    async def stop_timer(timer_id: str, labels: Dict[str, str]) -> float
    async def record_duration(name: str, duration_seconds: float, labels: Dict[str, str])
    async def record_custom_metric(name: str, value: Any, metric_type: str, labels: Dict[str, str])
    async def query_metrics(name: str, start_time: datetime, end_time: datetime, labels: Dict[str, str], aggregation: str) -> List[MetricData]
    async def get_metric_names(prefix: str) -> List[str]
    async def get_label_values(label_name: str, metric_name: str) -> List[str]
    async def delete_metric(name: str, labels: Dict[str, str])
    async def get_statistics(name: str, start_time: datetime, end_time: datetime, labels: Dict[str, str]) -> Dict[str, float]
    async def record_batch(metrics: List[Dict[str, Any]])
    async def flush()
    async def health_check() -> bool
```

#### Configuration Store Port
**File**: `config_store.py`

Data Models:
- `ProjectConfig` - Project-level configuration
- `AgentConfig` - Agent configuration
- `PipelineConfig` - Pipeline (workflow) configuration
- `WorkflowTemplate` - Workflow template
- `EnvironmentVariable` - Environment variable
- `MountedCommand` - Mounted command
- `MountedSubAgent` - Mounted sub-agent
- `ConfigVersion` - Version metadata

Operations:
- `get_project_config()`
- `get_agent_config()`
- `get_pipeline_config()`
- `list_projects()`
- `list_agents()`
- `list_pipelines()`
- `search_configs()`
- `get_config_version()`
- `list_config_versions()`
- `delete_project_config()`
- `delete_agent_config()`
- `exists()`

#### Other Output Ports
- **Container** (`container.py`) - Container runtime operations
- **Event Store** (`event_store.py`) - Event sourcing storage
- **LLM Provider** (`llm_provider.py`) - LLM integrations
- **Notifier** (`notifier.py`) - Event notifications
- **Repository** (`repository.py`) - Git operations
- **Storage** (`storage.py`) - Artifact storage
- **Ticket System** (`ticket_system.py`) - GitHub/Jira integration
- **Encryption Service** (`encryption_service.py`) - Secret encryption

---

## 3. Data Transfer Objects (DTOs)

### 3.1 DTO Structure

All DTOs are in `/workspace/src/codetoreum/adapters/primary/` and follow the pattern:

```
[domain]_dtos.py          # Request/Response models for a domain
[domain]_mappers.py       # Conversion between DTOs and domain objects
```

### 3.2 Agent DTOs
**File**: `agent_dtos.py`

Request Models:
- `CreateAgentRequest` - Create new agent
- `UpdateAgentRequest` - Update agent
- `AddCapabilityRequest` - Add capability
- `UpdateCapabilityRequest` - Update capability
- `AddMcpServerRequest` - Add MCP server
- `AgentCapabilityDTO` - Capability definition

Response Models:
- `AgentResponse` - Full agent details
- `AgentSummaryResponse` - Agent summary (for lists)
- `AgentListResponse` - Paginated list of agents
- `AgentCommandResult` - Operation result
- `AgentExecutionStatsDTO` - Execution statistics

### 3.3 Work Item DTOs
**File**: `work_item_dtos.py`

Request Models:
- `CreateWorkItemRequest` - Create work item
- `UpdateWorkItemRequest` - Update work item

Response Models:
- `WorkItemResponse` - Work item details
- `WorkItemDetailResponse` - Detailed view with history
- `WorkItemListResponse` - Paginated list with metadata
- `WorkItemCommandResult` - Operation result

### 3.4 Workflow DTOs
**File**: `workflow_dtos.py`

Request Models:
- `CreateWorkflowRequest` - Create workflow
- `UpdateWorkflowRequest` - Update workflow
- `StageDTO` - Workflow stage definition
- `TransitionDTO` - Stage transition
- `EntryConditionDTO` - Entry condition

Response Models:
- `WorkflowResponse` - Workflow details
- `WorkflowListResponse` - Paginated list
- `WorkflowVersionListResponse` - Version history
- `WorkflowCommandResult` - Operation result
- `WorkflowValidationResponse` - Validation results

### 3.5 Execution DTOs
**File**: `execution_dtos.py`

Request Models:
- `TerminateExecutionRequest` - Terminate execution
- `PauseExecutionRequest` - Pause execution
- `ResumeExecutionRequest` - Resume execution

Response Models:
- `ExecutionResponse` - Execution details
- `ExecutionListResponse` - Paginated list
- `ExecutionLogsResponse` - Execution logs
- `ExecutionHistoryResponse` - Execution history
- `ExecutionCommandResult` - Operation result

### 3.6 Orchestration DTOs
**File**: `orchestration_dtos.py`

Request Models:
- `StartWorkflowExecutionRequest` - Start execution
- `CancelWorkflowExecutionRequest` - Cancel execution
- `PauseWorkflowExecutionRequest` - Pause execution
- `ResumeWorkflowExecutionRequest` - Resume execution
- `EntryConditionValidationRequest` - Validate entry conditions

Response Models:
- `StartWorkflowExecutionResponse` - Execution started
- `WorkflowExecutionResponse` - Execution status
- `EntryConditionValidationResponse` - Validation result

### 3.7 Common API Models
**File**: `api_models.py`

Base Models:
- `BaseResponse` - Base response class
- `SuccessResponse` - Generic success response
- `ErrorResponse` - Standardized error response
- `ErrorDetail` - Detailed error information
- `ErrorCode` - Standard error code constants

Health Check:
- `HealthCheckResponse` - Service health status
- `ReadinessCheckResponse` - Service readiness

Authentication:
- `TokenInfoResponse` - Token information

Pagination:
- `PaginationParams` - Standard pagination parameters
- `PaginatedResponse` - Base class for paginated responses

---

## 4. Authentication and Dependency Injection

### 4.1 Authentication System

**Type**: Simple Token Authentication (JupyterLab-style)

Location: `/workspace/src/codetoreum/adapters/primary/simple_auth_dependencies.py`

Features:
- Single-token authentication (not multi-user)
- Token printed to console on startup
- Supports both header and query parameter auth
- Token validation with format pre-check to prevent CPU abuse

```python
class SimpleAuthDependencies:
    """FastAPI dependencies for simple token authentication"""
    
    async def require_auth(
        self,
        authorization: Optional[str] = Header(None),
        token: Optional[str] = Query(None)
    ) -> bool:
        """Require authentication - raises 401 if missing/invalid"""
        pass
    
    async def optional_auth(
        self,
        authorization: Optional[str] = Header(None),
        token: Optional[str] = Query(None)
    ) -> bool:
        """Optional authentication - returns False if missing/invalid"""
        pass
```

### 4.2 How Authentication Works

1. **Initialization** (in `fastapi_app.py`):
```python
auth_manager = SimpleTokenAuthManager(secret_key=auth_secret_key)
auth_deps = SimpleAuthDependencies(auth_manager)
app.state.auth_manager = auth_manager
app.state.auth_deps = auth_deps
```

2. **Usage on Routers**:
```python
router_kwargs = {
    "prefix": "/api/v2/work-items",
    "tags": ["work-items"],
}
if auth_deps:
    router_kwargs["dependencies"] = [Depends(auth_deps.require_auth)]

router = APIRouter(**router_kwargs)
```

3. **Token Validation Flow**:
   - Check query parameter `?token=...`
   - Check Authorization header `Bearer ...`
   - Pre-validate JWT format (3 dot-separated parts)
   - Validate token signature

4. **Authentication Locations**:
   - Header: `Authorization: Bearer <token>`
   - Query: `?token=<token>`

### 4.3 Dependency Injection Pattern

All routers use factory functions:

```python
def create_work_items_router(
    command_port: IWorkItemCommandPort,
    query_port: IWorkItemQueryPort,
    auth_deps: Optional[SimpleAuthDependencies] = None
) -> APIRouter:
    """Create configured router with dependencies injected"""
    # Create router with optional auth
    router = APIRouter(...)
    
    # Register endpoints using injected dependencies
    @router.get("")
    async def list_work_items(...):
        # Use ports
        result = await query_port.list_work_items(...)
    
    return router
```

Dependencies are provided at application creation:
```python
app = create_app(
    workflow_command_port=workflow_port,
    task_query_port=task_query_port,
    config_command_port=config_command_port,
    # ... more ports ...
    auth_deps=auth_deps
)
```

---

## 5. FastAPI Application Structure

### 5.1 App Creation Flow

Location: `/workspace/src/codetoreum/adapters/primary/fastapi_app.py`

```python
def create_app(
    # Input ports
    workflow_command_port: IWorkflowCommandPort,
    task_query_port: ITaskQueryPort,
    config_command_port: IConfigurationCommandPort,
    work_item_command_port: IWorkItemCommandPort,
    work_item_query_port: IWorkItemQueryPort,
    workflow_query_port: IWorkflowQueryPort,
    workflow_definition_command_port: IWorkflowDefinitionCommandPort,
    orchestration_command_port: IOrchestrationCommandPort,
    agent_command_port: IAgentCommandPort,
    agent_query_port: IAgentQueryPort,
    execution_command_port: IExecutionCommandPort,
    execution_query_port: IExecutionQueryPort,
    # Infrastructure
    event_bus: IEventBus,
    config_service: IConfigurationService,
    logger: ILogger,
    # Configuration
    auth_secret_key: Optional[str] = None,
    disable_auth: bool = False,
    cors_origins: Optional[list] = None
) -> FastAPI:
```

### 5.2 Middleware Stack

1. **Security Headers Middleware** - Adds X-Content-Type-Options, X-Frame-Options, HSTS, CSP
2. **Error Handling Middleware** - Standardized error responses
3. **CORS Middleware** - Cross-origin request handling
4. **Rate Limiting** - SlowAPI middleware with 100/minute default
5. **Authentication** - Optional token validation on protected endpoints

### 5.3 Endpoint Categories

#### Unauthenticated Endpoints
- `GET /api/v2/health` - Health check
- `GET /api/v2/health/ready` - Readiness check
- `POST /webhooks/github` - GitHub webhook receiver
- `WebSocket /api/v2/events/stream` - Real-time event streaming

#### Authenticated Endpoints
- All `/api/v2/*` endpoints (unless overridden)
- All `/api/v1/*` endpoints (legacy REST API)

### 5.4 Router Registration Order

```python
# 1. REST API adapter (legacy endpoints) - /api/v1
app.include_router(rest_api_adapter.router)

# 2. Work Items - /api/v2/work-items
app.include_router(work_items_router)

# 3. Workflows - /api/v2/workflows
app.include_router(workflows_router)

# 4. Orchestrator - /api/v2/orchestrator
app.include_router(orchestrator_router)

# 5. Scheduler - /api/v2/scheduler
app.include_router(scheduler_router)

# 6. Agents - /api/v2/agents
app.include_router(agents_router)

# 7. Executions - /api/v2/executions
app.include_router(executions_router)
```

### 5.5 WebSocket Support

Real-time event streaming via WebSocket:
- Endpoint: `GET /api/v2/events/stream`
- Query parameter: `?token=...` for authentication
- Subscription support for filtering events
- Flow control with buffer management
- Heartbeat/keepalive every 30 seconds

---

## 6. DTO Mapper Pattern

### 6.1 Mapper Structure

Each domain has a mapper class:

```python
class WorkItemMapper:
    """Convert between WorkItem domain objects and DTOs"""
    
    @staticmethod
    def to_response(domain_obj: WorkItem) -> WorkItemResponse:
        """Convert domain object to API response"""
        return WorkItemResponse(
            id=domain_obj.id,
            project_id=domain_obj.project_id,
            # ... field mappings ...
        )
    
    @staticmethod
    def to_create_command(request: CreateWorkItemRequest) -> CreateWorkItemCommand:
        """Convert API request to domain command"""
        return CreateWorkItemCommand(
            project_id=request.project_id,
            title=request.title,
            # ... field mappings ...
        )
```

### 6.2 Benefits

1. **Decoupling** - API contracts independent from domain
2. **Flexibility** - API can evolve without affecting domain
3. **Validation** - Input validation at API boundary
4. **Transformation** - Handle field conversions (e.g., enums)
5. **Security** - Sensitive fields masked in responses

---

## 7. REST API Adapter (Legacy)

Location: `/workspace/src/codetoreum/adapters/primary/rest_api_adapter.py`

Prefix: `/api/v1`

Provides backward-compatible endpoints for:

### Workflow Control
- `POST /workflows` - Start workflow
- `POST /workflows/{id}/pause` - Pause
- `POST /workflows/{id}/resume` - Resume
- `POST /workflows/{id}/cancel` - Cancel
- `POST /workflows/{id}/retry` - Retry stage

### Execution Queries
- `GET /executions` - List executions
- `GET /executions/{id}` - Get execution status
- `GET /executions/{id}/artifacts` - Get artifacts

### Configuration Management
- `PATCH /configurations/projects/{name}` - Update project config
- `GET /configurations/projects/{name}` - Get project config
- `GET /configurations/agents` - List agent configs
- `GET /configurations/agents/{name}` - Get agent config
- `GET /configurations/pipelines` - List pipeline configs
- `GET /configurations/pipelines/{name}` - Get pipeline config
- `GET /configurations/history` - Get change history
- `POST /configurations/rollback/{id}` - Rollback configuration

---

## 8. Key Design Patterns

### 8.1 Hexagonal Architecture

```
API Layer (Routers)
    ↓
DTOs & Mappers
    ↓
Input Ports (Command & Query)
    ↓
Application Services
    ↓
Domain Objects
    ↓
Output Ports (Infrastructure)
```

### 8.2 Factory Pattern for Routers

```python
def create_xxx_router(
    command_port: IXxxCommandPort,
    query_port: IXxxQueryPort,
    auth_deps: Optional[SimpleAuthDependencies] = None
) -> APIRouter:
    """Factory function creates configured router"""
```

### 8.3 Dependency Injection

- Constructor injection for ports
- FastAPI Depends() for authentication
- App state for global services (auth_manager, rate_limiter)

### 8.4 Error Handling

- Global exception handler in fastapi_app.py
- Error middleware standardizes responses
- HTTPException for API errors
- Domain exceptions wrapped in 400-500 responses

---

## 9. Configuration and Environment

### 9.1 Environment Variables

```python
# Request handling
CODETOREUM_MAX_REQUEST_SIZE=10MB  # 10MB default

# Rate limiting
CODETOREUM_RATE_LIMIT=100/minute

# CORS
CODETOREUM_ALLOWED_ORIGINS=*  # or comma-separated list

# API
API_HOST=localhost
API_PORT=8000
API_USE_HTTPS=false

# Authentication
CODETOREUM_AUTH_SECRET=<random>  # Generated if not set
CODETOREUM_DISABLE_AUTH=false    # For testing only
```

### 9.2 Configuration Constants

Location: `/workspace/src/codetoreum/adapters/primary/rest_api/common/config.py`

```python
MAX_PAGE_SIZE = 100
DEFAULT_PAGE_SIZE = 20
DEFAULT_TIMEOUT = 300  # 5 minutes
LONG_RUNNING_TIMEOUT = 3600  # 1 hour
DEFAULT_RATE_LIMIT = 100  # per minute
```

---

## 10. File Structure Summary

```
/workspace/src/codetoreum/adapters/primary/
├── fastapi_app.py                    # Main app factory
├── rest_api_adapter.py               # Legacy /api/v1 endpoints
├── websocket_adapter.py              # WebSocket handling
├── github_webhook_adapter.py         # GitHub webhook receiver
├── auth_api_adapter.py               # Auth endpoints
├── simple_auth_dependencies.py       # Auth dependency injection
├── error_middleware.py               # Error handling
├── api_models.py                     # Common DTOs
├── agent_dtos.py                     # Agent DTOs
├── agent_mappers.py                  # Agent mappers
├── work_item_dtos.py                 # Work item DTOs
├── work_item_mappers.py              # Work item mappers
├── workflow_dtos.py                  # Workflow DTOs
├── workflow_mappers.py               # Workflow mappers
├── execution_dtos.py                 # Execution DTOs
├── execution_mappers.py              # Execution mappers
├── orchestration_dtos.py             # Orchestration DTOs
├── rest_api/
│   └── common/
│       ├── auth.py                   # Auth helpers
│       ├── config.py                 # Config constants
│       └── errors.py                 # Error definitions
└── routers/
    ├── __init__.py
    ├── work_items.py                 # Work items endpoints
    ├── workflows.py                  # Workflow endpoints
    ├── orchestrator.py               # Orchestration endpoints
    ├── agents.py                     # Agent endpoints
    ├── executions.py                 # Execution endpoints
    ├── scheduler.py                  # Scheduler endpoints
    └── events.py                     # Event streaming endpoints

/workspace/src/codetoreum/ports/
├── input/                            # Command & Query ports
│   ├── config_command.py             # Configuration commands
│   ├── work_item_command.py          # Work item commands
│   ├── work_item_query.py            # Work item queries
│   ├── workflow_definition_command.py # Workflow commands
│   ├── workflow_query.py             # Workflow queries
│   ├── agent_command.py              # Agent commands
│   ├── agent_query.py                # Agent queries
│   ├── execution_command.py          # Execution commands
│   ├── execution_query.py            # Execution queries
│   ├── orchestration_command.py      # Orchestration commands
│   ├── task_query.py                 # Legacy task queries
│   └── workflow_command.py           # Legacy workflow commands
└── output/                           # Infrastructure ports
    ├── metrics.py                    # Metrics collection
    ├── config_store.py               # Configuration storage
    ├── container.py                  # Container runtime
    ├── event_store.py                # Event sourcing
    ├── llm_provider.py               # LLM integration
    ├── storage.py                    # Artifact storage
    ├── repository.py                 # Git operations
    ├── notifier.py                   # Notifications
    ├── ticket_system.py              # GitHub/Jira
    └── encryption_service.py         # Secret encryption
```

---

## 11. Phase 6 Dependencies

Based on the current implementation, Phase 6 (Configuration, Metrics, Workspace Management) will need:

### 11.1 Input Ports Already Available
- `IConfigurationCommandPort` - For configuration mutations
- Existing mappers and DTOs framework

### 11.2 Output Ports Already Available
- `IMetrics` - Metrics collection interface
- `IConfigStore` - Configuration storage interface

### 11.3 Gaps to Fill
1. **Configuration Query Port** - Need read-only configuration queries (currently only in legacy adapter)
2. **Metrics Query Endpoints** - Queries for metrics data (interface exists, but no router)
3. **Workspace Management** - Commands and queries for workspace operations
4. **Status/Statistics Endpoints** - System health and statistics
5. **Configuration UI/Schema Endpoints** - Configuration schema and defaults

### 11.4 Recommended Phase 6 Routers
1. `routers/configurations.py` - `/api/v2/configurations` - Config management
2. `routers/metrics.py` - `/api/v2/metrics` - Metrics queries and statistics
3. `routers/workspace.py` - `/api/v2/workspace` - Workspace operations
4. `routers/system.py` - `/api/v2/system` - System status and statistics

---

## 12. Quick Start: Building Phase 6 Endpoints

### 12.1 Template for New Router

```python
# routers/configurations.py
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from codetoreum.adapters.primary.simple_auth_dependencies import SimpleAuthDependencies
from codetoreum.ports.input.config_command import IConfigurationCommandPort

def create_configurations_router(
    command_port: IConfigurationCommandPort,
    auth_deps: Optional[SimpleAuthDependencies] = None,
) -> APIRouter:
    """Create configurations REST API router"""
    
    router_kwargs = {
        "prefix": "/api/v2/configurations",
        "tags": ["configurations"],
    }
    if auth_deps:
        router_kwargs["dependencies"] = [Depends(auth_deps.require_auth)]
    
    router = APIRouter(**router_kwargs)
    
    @router.get("", summary="List configurations")
    async def list_configurations(...):
        """Implementation"""
        pass
    
    return router
```

### 12.2 Register in App

```python
# In fastapi_app.py, after other routers:
configurations_router = create_configurations_router(
    command_port=config_command_port,
    auth_deps=auth_deps,
)
app.include_router(configurations_router)
```

### 12.3 DTO Pattern

```python
# configurations_dtos.py
from pydantic import BaseModel, Field

class GetConfigurationRequest(BaseModel):
    """Request to get configuration"""
    config_type: str = Field(..., description="Type: project, agent, pipeline")
    config_id: str = Field(..., description="Configuration ID")

class ConfigurationResponse(BaseModel):
    """Configuration response"""
    id: str
    type: str
    data: dict
    version: int
    created_at: datetime
    updated_at: datetime
```

---

## Summary of Current Capabilities

**Available Now**:
- RESTful CRUD for work items, workflows, agents
- Workflow orchestration (start, pause, resume, cancel)
- Execution monitoring with logs and history
- Authentication with simple token-based auth
- Error handling and validation
- Pagination, filtering, and sorting
- WebSocket for real-time events
- GitHub webhook integration
- Rate limiting and CORS support

**Missing for Phase 6**:
- Configuration query endpoints (only commands exist)
- Metrics query endpoints (interface exists, no router)
- Workspace management operations
- System statistics and health dashboard
- Configuration schema/defaults endpoints
- Environment variable management UI support
- Mounted commands and sub-agents management

This structure provides a solid foundation for Phase 6 implementation.
