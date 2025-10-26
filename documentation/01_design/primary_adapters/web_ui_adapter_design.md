# Web UI Adapter Design

## Purpose

The Web UI Adapter provides HTTP REST API and WebSocket interfaces for the web-based user interface. It replaces and enhances the legacy `ObservabilityServer` with comprehensive query capabilities, real-time streaming, and configuration management.

## Architecture Position

```
┌──────────────────┐
│   Web Browser    │
│   (React/Vue)    │
└────┬─────────┬───┘
     │         │
     │ HTTP    │ WebSocket
     │ REST    │ Real-time
     ▼         ▼
┌────────────────────────┐
│  Web UI Adapter        │ ← Primary Adapter
│  (FastAPI + WebSocket) │
└────┬──────────────┬────┘
     │              │
     ▼              ▼
┌────────────────────────┐
│    Input Ports         │
│  - TaskQueryPort       │
│  - ProjectQueryPort    │
│  - MetricsQueryPort    │
│  - EventStreamPort     │
│  - LogStreamPort       │
│  - ConfigCommandPort   │
│  - AgentCommandPort    │
└────────────────────────┘
```

## Responsibilities

### Primary Responsibilities
1. **REST API**: Provide RESTful endpoints for queries and commands
2. **WebSocket Streaming**: Real-time event and log streaming
3. **Authentication**: User session management
4. **Authorization**: Role-based access control
5. **Request Validation**: Input validation and sanitization
6. **Response Formatting**: JSON serialization and pagination
7. **CORS Handling**: Cross-origin resource sharing
8. **API Documentation**: OpenAPI/Swagger specs

### Non-Responsibilities
- Business logic (handled by domain layer)
- Data persistence (handled by infrastructure)
- Event processing (handled by application services)
- Frontend rendering (handled by separate UI app)

## Interface Design

### REST API Endpoints

#### Projects

```
GET    /api/v1/projects
GET    /api/v1/projects/{project_id}
POST   /api/v1/projects
PATCH  /api/v1/projects/{project_id}
DELETE /api/v1/projects/{project_id}
```

#### Workflows

```
GET    /api/v1/workflows
GET    /api/v1/workflows/{workflow_id}
POST   /api/v1/workflows
POST   /api/v1/workflows/{workflow_id}/cancel
POST   /api/v1/workflows/{workflow_id}/retry
GET    /api/v1/workflows/{workflow_id}/stages
GET    /api/v1/workflows/{workflow_id}/events
```

#### Tasks

```
GET    /api/v1/tasks
GET    /api/v1/tasks/{task_id}
GET    /api/v1/tasks/{task_id}/logs
POST   /api/v1/tasks/{task_id}/cancel
```

#### Agents

```
GET    /api/v1/agents
GET    /api/v1/agents/{agent_id}
GET    /api/v1/agents/{agent_id}/executions
POST   /api/v1/agents/{agent_id}/execute
POST   /api/v1/agents/{agent_id}/executions/{execution_id}/cancel
```

#### Metrics

```
GET    /api/v1/metrics/system
GET    /api/v1/metrics/workflows
GET    /api/v1/metrics/agents
GET    /api/v1/metrics/tasks
```

#### Configuration

```
GET    /api/v1/config
PATCH  /api/v1/config
POST   /api/v1/config/validate
GET    /api/v1/config/templates
```

### WebSocket Endpoints

```
WS     /ws/events                # Event stream
WS     /ws/logs                  # Log stream
WS     /ws/metrics               # Metrics stream
WS     /ws/agents/{id}/output    # Agent output stream
```

## Implementation Design

### Class Structure

```python
from fastapi import FastAPI, WebSocket, Depends, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from typing import List, Optional
from pydantic import BaseModel
import asyncio

class WebUIAdapter:
    """
    FastAPI-based web UI adapter providing REST and WebSocket APIs.
    """

    def __init__(
        self,
        task_query_port: ITaskQueryPort,
        project_query_port: IProjectQueryPort,
        metrics_query_port: IMetricsQueryPort,
        event_stream_port: IEventStreamPort,
        log_stream_port: ILogStreamPort,
        config_command_port: IConfigCommandPort,
        agent_command_port: IAgentCommandPort,
        workflow_command_port: IWorkflowCommandPort,
        auth_service: IAuthenticationService,
        logger: ILogger
    ):
        """Initialize adapter with dependencies."""
        self.task_query = task_query_port
        self.project_query = project_query_port
        self.metrics_query = metrics_query_port
        self.event_stream = event_stream_port
        self.log_stream = log_stream_port
        self.config_command = config_command_port
        self.agent_command = agent_command_port
        self.workflow_command = workflow_command_port
        self.auth = auth_service
        self.logger = logger

        # WebSocket connection managers
        self.event_connections: Dict[str, WebSocket] = {}
        self.log_connections: Dict[str, WebSocket] = {}

        # Create FastAPI app
        self.app = self._create_app()

    def _create_app(self) -> FastAPI:
        """Create and configure FastAPI application."""
        app = FastAPI(
            title="Codetoreum API",
            version="1.0.0",
            description="API for Codetoreum workflow orchestration"
        )

        # CORS middleware
        app.add_middleware(
            CORSMiddleware,
            allow_origins=["http://localhost:3000"],  # From config
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )

        # Register routes
        self._register_routes(app)

        return app

    def _register_routes(self, app: FastAPI):
        """Register all API routes."""

        # Health check
        @app.get("/health")
        async def health_check():
            return {"status": "healthy"}

        # Projects
        @app.get("/api/v1/projects")
        async def list_projects(
            auth: AuthContext = Depends(self.get_auth_context),
            limit: int = Query(50, ge=1, le=100),
            offset: int = Query(0, ge=0)
        ) -> ProjectListResponse:
            """List all projects."""
            query = ListProjectsQuery(
                user_id=auth.user_id,
                limit=limit,
                offset=offset
            )
            result = await self.project_query.list_projects(query)
            return self._format_project_list_response(result)

        @app.get("/api/v1/projects/{project_id}")
        async def get_project(
            project_id: str,
            auth: AuthContext = Depends(self.get_auth_context)
        ) -> ProjectResponse:
            """Get project details."""
            query = GetProjectQuery(project_id=project_id)
            result = await self.project_query.get_project(query)

            if not result:
                raise HTTPException(status_code=404, detail="Project not found")

            return self._format_project_response(result)

        # Workflows
        @app.get("/api/v1/workflows")
        async def list_workflows(
            auth: AuthContext = Depends(self.get_auth_context),
            project_id: Optional[str] = None,
            status: Optional[str] = None,
            limit: int = Query(50, ge=1, le=100),
            offset: int = Query(0, ge=0)
        ) -> WorkflowListResponse:
            """List workflows with optional filtering."""
            query = ListWorkflowsQuery(
                user_id=auth.user_id,
                project_id=project_id,
                status=status,
                limit=limit,
                offset=offset
            )
            result = await self.task_query.list_workflows(query)
            return self._format_workflow_list_response(result)

        @app.post("/api/v1/workflows")
        async def start_workflow(
            request: StartWorkflowRequest,
            auth: AuthContext = Depends(self.get_auth_context)
        ) -> WorkflowResponse:
            """Start a new workflow."""
            command = StartWorkflowCommand(
                project_name=request.project_name,
                work_item_id=request.work_item_id,
                pipeline_name=request.pipeline_name,
                stage_name=request.stage_name,
                user_id=auth.user_id
            )

            result = await self.workflow_command.start_workflow(command, auth)
            return self._format_workflow_response(result)

        @app.post("/api/v1/workflows/{workflow_id}/cancel")
        async def cancel_workflow(
            workflow_id: str,
            auth: AuthContext = Depends(self.get_auth_context)
        ):
            """Cancel a running workflow."""
            command = CancelWorkflowCommand(
                workflow_id=workflow_id,
                user_id=auth.user_id
            )

            await self.workflow_command.cancel_workflow(command, auth)
            return {"status": "cancelled", "workflow_id": workflow_id}

        # Tasks
        @app.get("/api/v1/tasks")
        async def list_tasks(
            auth: AuthContext = Depends(self.get_auth_context),
            project_id: Optional[str] = None,
            agent: Optional[str] = None,
            status: Optional[str] = None,
            limit: int = Query(50, ge=1, le=100),
            offset: int = Query(0, ge=0)
        ) -> TaskListResponse:
            """List tasks with filtering."""
            query = ListTasksQuery(
                user_id=auth.user_id,
                project_id=project_id,
                agent=agent,
                status=status,
                limit=limit,
                offset=offset
            )
            result = await self.task_query.list_tasks(query)
            return self._format_task_list_response(result)

        @app.get("/api/v1/tasks/{task_id}")
        async def get_task(
            task_id: str,
            auth: AuthContext = Depends(self.get_auth_context)
        ) -> TaskResponse:
            """Get task details."""
            query = GetTaskQuery(task_id=task_id)
            result = await self.task_query.get_task(query)

            if not result:
                raise HTTPException(status_code=404, detail="Task not found")

            return self._format_task_response(result)

        @app.get("/api/v1/tasks/{task_id}/logs")
        async def get_task_logs(
            task_id: str,
            auth: AuthContext = Depends(self.get_auth_context),
            limit: int = Query(100, ge=1, le=1000)
        ) -> LogResponse:
            """Get task logs."""
            query = GetTaskLogsQuery(task_id=task_id, limit=limit)
            result = await self.log_stream.get_logs(query)
            return self._format_log_response(result)

        # Agents
        @app.get("/api/v1/agents")
        async def list_agents(
            auth: AuthContext = Depends(self.get_auth_context)
        ) -> AgentListResponse:
            """List available agents."""
            query = ListAgentsQuery()
            result = await self.agent_command.list_agents(query)
            return self._format_agent_list_response(result)

        @app.post("/api/v1/agents/{agent_id}/execute")
        async def execute_agent(
            agent_id: str,
            request: ExecuteAgentRequest,
            auth: AuthContext = Depends(self.get_auth_context)
        ) -> ExecutionResponse:
            """Execute an agent manually."""
            command = ExecuteAgentCommand(
                agent_name=agent_id,
                project_name=request.project_name,
                work_item_id=request.work_item_id,
                context=request.context,
                user_id=auth.user_id
            )

            result = await self.agent_command.execute_agent(command, auth)
            return self._format_execution_response(result)

        @app.post("/api/v1/agents/{agent_id}/executions/{execution_id}/cancel")
        async def cancel_agent_execution(
            agent_id: str,
            execution_id: str,
            auth: AuthContext = Depends(self.get_auth_context)
        ):
            """Cancel agent execution."""
            command = CancelAgentCommand(
                execution_id=execution_id,
                user_id=auth.user_id
            )

            await self.agent_command.cancel_agent(command, auth)
            return {"status": "cancelled", "execution_id": execution_id}

        # Metrics
        @app.get("/api/v1/metrics/system")
        async def get_system_metrics(
            auth: AuthContext = Depends(self.get_auth_context)
        ) -> MetricsResponse:
            """Get system-wide metrics."""
            query = GetSystemMetricsQuery()
            result = await self.metrics_query.get_system_metrics(query)
            return self._format_metrics_response(result)

        # Configuration
        @app.get("/api/v1/config")
        async def get_configuration(
            auth: AuthContext = Depends(self.get_auth_context)
        ) -> ConfigResponse:
            """Get system configuration."""
            query = GetConfigQuery()
            result = await self.config_command.get_config(query)
            return self._format_config_response(result)

        # WebSocket endpoints
        @app.websocket("/ws/events")
        async def websocket_events(websocket: WebSocket):
            """WebSocket endpoint for event streaming."""
            await self._handle_event_websocket(websocket)

        @app.websocket("/ws/logs")
        async def websocket_logs(websocket: WebSocket):
            """WebSocket endpoint for log streaming."""
            await self._handle_log_websocket(websocket)

        @app.websocket("/ws/agents/{agent_id}/output")
        async def websocket_agent_output(websocket: WebSocket, agent_id: str):
            """WebSocket endpoint for agent output streaming."""
            await self._handle_agent_output_websocket(websocket, agent_id)

    async def _handle_event_websocket(self, websocket: WebSocket):
        """Handle WebSocket connection for event streaming."""
        await websocket.accept()

        connection_id = str(uuid.uuid4())
        self.event_connections[connection_id] = websocket

        try:
            # Subscribe to event stream
            filters = await self._get_event_filters(websocket)

            async for event in self.event_stream.subscribe(filters):
                # Translate to external format
                external_event = self._translate_event(event)

                # Send to client
                await websocket.send_json(external_event)

        except WebSocketDisconnect:
            self.logger.info(f"Event WebSocket disconnected: {connection_id}")
        finally:
            del self.event_connections[connection_id]

    async def _handle_log_websocket(self, websocket: WebSocket):
        """Handle WebSocket connection for log streaming."""
        await websocket.accept()

        connection_id = str(uuid.uuid4())
        self.log_connections[connection_id] = websocket

        try:
            # Subscribe to log stream
            filters = await self._get_log_filters(websocket)

            async for log_entry in self.log_stream.subscribe(filters):
                # Translate to external format
                external_log = self._translate_log(log_entry)

                # Send to client
                await websocket.send_json(external_log)

        except WebSocketDisconnect:
            self.logger.info(f"Log WebSocket disconnected: {connection_id}")
        finally:
            del self.log_connections[connection_id]

    async def get_auth_context(
        self,
        authorization: str = Header(None)
    ) -> AuthContext:
        """
        Dependency for authentication.

        Extracts auth context from authorization header.
        """
        if not authorization:
            raise HTTPException(status_code=401, detail="Authorization required")

        try:
            # Parse token (JWT or session cookie)
            auth_context = await self.auth.authenticate(authorization)
            return auth_context
        except AuthenticationError:
            raise HTTPException(status_code=401, detail="Invalid credentials")

    def _format_project_list_response(
        self,
        projects: List[ProjectView]
    ) -> ProjectListResponse:
        """Format project list response."""
        return {
            "data": [
                {
                    "id": p.id,
                    "type": "project",
                    "attributes": {
                        "name": p.name,
                        "description": p.description,
                        "status": p.status
                    },
                    "links": {
                        "self": f"/api/v1/projects/{p.id}"
                    }
                }
                for p in projects
            ],
            "meta": {
                "total": len(projects),
                "limit": 50,
                "offset": 0
            }
        }

# Request/Response Models
class StartWorkflowRequest(BaseModel):
    """Request to start workflow."""
    project_name: str
    work_item_id: str
    pipeline_name: str
    stage_name: Optional[str] = None

class ExecuteAgentRequest(BaseModel):
    """Request to execute agent."""
    project_name: str
    work_item_id: str
    context: Dict[str, Any] = {}

class ProjectListResponse(BaseModel):
    """Response for project list."""
    data: List[Dict[str, Any]]
    meta: Dict[str, Any]

class WorkflowResponse(BaseModel):
    """Response for workflow operation."""
    id: str
    status: str
    created_at: str
    links: Dict[str, str]
```

## Authentication & Authorization

### Authentication Methods

1. **Session Cookies** (Web UI):
```python
@app.post("/api/v1/auth/login")
async def login(credentials: LoginRequest):
    user = await auth_service.authenticate_user(
        credentials.username,
        credentials.password
    )

    if not user:
        raise HTTPException(status_code=401, detail="Invalid credentials")

    # Create session
    session_id = await auth_service.create_session(user.id)

    response = JSONResponse({"status": "authenticated"})
    response.set_cookie(
        key="session_id",
        value=session_id,
        httponly=True,
        secure=True,
        samesite="strict"
    )

    return response
```

2. **JWT Tokens** (API clients):
```python
@app.post("/api/v1/auth/token")
async def get_token(credentials: LoginRequest):
    user = await auth_service.authenticate_user(
        credentials.username,
        credentials.password
    )

    if not user:
        raise HTTPException(status_code=401, detail="Invalid credentials")

    # Generate JWT
    token = create_access_token(
        data={"sub": user.id, "roles": user.roles}
    )

    return {"access_token": token, "token_type": "bearer"}
```

3. **API Keys** (Service accounts):
```python
async def verify_api_key(x_api_key: str = Header(...)):
    key_info = await auth_service.validate_api_key(x_api_key)

    if not key_info:
        raise HTTPException(status_code=401, detail="Invalid API key")

    return AuthContext(
        user_id=key_info.service_account_id,
        roles=key_info.roles,
        permissions=key_info.permissions
    )
```

### Authorization

```python
def requires_permission(permission: str):
    """Decorator for permission checking."""
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, auth: AuthContext, **kwargs):
            if permission not in auth.permissions:
                raise HTTPException(
                    status_code=403,
                    detail=f"Missing permission: {permission}"
                )
            return await func(*args, auth=auth, **kwargs)
        return wrapper
    return decorator

@app.post("/api/v1/workflows")
@requires_permission("workflow:start")
async def start_workflow(...):
    pass
```

## Error Handling

### Standard Error Response

```json
{
  "error": {
    "type": "ValidationError",
    "message": "Invalid request data",
    "details": {
      "field": "project_name",
      "issue": "required field missing"
    },
    "request_id": "req-123",
    "timestamp": "2025-10-26T12:00:00Z"
  }
}
```

### Exception Handlers

```python
@app.exception_handler(ValidationError)
async def validation_exception_handler(request: Request, exc: ValidationError):
    return JSONResponse(
        status_code=400,
        content={
            "error": {
                "type": "ValidationError",
                "message": str(exc),
                "request_id": request.state.request_id
            }
        }
    )

@app.exception_handler(AuthorizationError)
async def authorization_exception_handler(request: Request, exc: AuthorizationError):
    return JSONResponse(
        status_code=403,
        content={
            "error": {
                "type": "AuthorizationError",
                "message": "Insufficient permissions",
                "request_id": request.state.request_id
            }
        }
    )
```

## Testing Strategy

### Unit Tests
```python
from fastapi.testclient import TestClient

class TestWebUIAdapter:
    def setup_method(self):
        # Create adapter with mock ports
        self.adapter = create_test_adapter()
        self.client = TestClient(self.adapter.app)

    def test_list_projects(self):
        """Test project list endpoint."""
        response = self.client.get(
            "/api/v1/projects",
            headers={"Authorization": "Bearer test-token"}
        )

        assert response.status_code == 200
        data = response.json()
        assert "data" in data
        assert isinstance(data["data"], list)

    def test_start_workflow(self):
        """Test workflow start endpoint."""
        response = self.client.post(
            "/api/v1/workflows",
            json={
                "project_name": "test-project",
                "work_item_id": "123",
                "pipeline_name": "dev"
            },
            headers={"Authorization": "Bearer test-token"}
        )

        assert response.status_code == 200
        data = response.json()
        assert "id" in data
```

### WebSocket Tests
```python
@pytest.mark.asyncio
async def test_event_websocket():
    """Test event WebSocket streaming."""
    async with websocket_connect("ws://test/ws/events") as ws:
        # Subscribe to events
        await ws.send_json({"filters": {"event_type": "workflow_started"}})

        # Receive event
        event = await ws.receive_json()
        assert event["type"] == "workflow_started"
```

## Observability

### Metrics
```python
# HTTP request metrics
http_requests_total = Counter(
    'http_requests_total',
    'Total HTTP requests',
    ['method', 'endpoint', 'status']
)

http_request_duration_seconds = Histogram(
    'http_request_duration_seconds',
    'HTTP request duration',
    ['method', 'endpoint']
)

# WebSocket metrics
websocket_connections_active = Gauge(
    'websocket_connections_active',
    'Active WebSocket connections',
    ['endpoint']
)
```

## Configuration

```yaml
web_ui:
  enabled: true
  host: "0.0.0.0"
  port: 5000
  cors:
    origins:
      - "http://localhost:3000"
      - "https://app.codetoreum.com"
  auth:
    session_secret: "${SESSION_SECRET}"
    jwt_secret: "${JWT_SECRET}"
    token_expiry: "24h"
  rate_limiting:
    enabled: true
    requests_per_minute: 60
```

## Summary

The Web UI Adapter provides:
- **REST API** for CRUD operations
- **WebSocket streaming** for real-time updates
- **Authentication** via sessions, JWT, or API keys
- **Authorization** via RBAC
- **Comprehensive endpoints** for all system operations
- **OpenAPI documentation** for API consumers

This adapter enables rich web-based user interfaces while maintaining clean separation from the domain core.
