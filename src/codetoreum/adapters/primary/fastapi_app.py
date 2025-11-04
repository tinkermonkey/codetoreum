"""
FastAPI Application Setup

This module sets up the FastAPI application with all primary adapters,
including webhook endpoints, REST API, and WebSocket support.

Authentication:
--------------
Uses a simplified JupyterLab-style single-token authentication system.
On startup, the server generates a token and prints an authentication URL
to the console. Users can click this URL or use the token in API requests.

This is NOT a multi-user system - it's designed for single-tenant deployments
and development environments.
"""

import os
from contextlib import asynccontextmanager
from typing import Any, Dict, Optional

from fastapi import Depends, FastAPI, Header, Request, WebSocket
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware
from slowapi.util import get_remote_address
from starlette.middleware.base import BaseHTTPMiddleware

from codetoreum.adapters.primary.api_models import (
    HealthCheckResponse,
    ReadinessCheckResponse,
    TokenInfoResponse,
)
from codetoreum.adapters.primary.error_middleware import error_handling_middleware
from codetoreum.adapters.primary.github_webhook_adapter import (
    GitHubWebhookAdapter,
    IConfigurationService,
    IEventBus,
    ILogger,
)
from codetoreum.adapters.primary.rest_api_adapter import RestAPIAdapter
from codetoreum.adapters.primary.simple_auth_dependencies import SimpleAuthDependencies
from codetoreum.adapters.primary.websocket_adapter import WebSocketAdapter
from codetoreum.adapters.primary.routers.work_items import create_work_items_router
from codetoreum.infrastructure.auth import SimpleTokenAuthManager
from codetoreum.ports.input.config_command import IConfigurationCommandPort
from codetoreum.ports.input.task_query import ITaskQueryPort
from codetoreum.ports.input.workflow_command import IWorkflowCommandPort
from codetoreum.ports.input.work_item_command import IWorkItemCommandPort
from codetoreum.ports.input.work_item_query import IWorkItemQueryPort


# ============================================================================
# Security Headers Middleware
# ============================================================================


async def security_headers_middleware(request: Request, call_next):
    """
    Add security headers to all responses.

    Headers added:
    - X-Content-Type-Options: nosniff - Prevents MIME type sniffing
    - X-Frame-Options: DENY - Prevents clickjacking
    - X-XSS-Protection: 1; mode=block - Enables XSS filtering
    - Strict-Transport-Security: Enforces HTTPS (if enabled)
    - Content-Security-Policy: Restricts resource loading
    """
    response = await call_next(request)

    # Security headers
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["X-XSS-Protection"] = "1; mode=block"

    # Add HSTS header if using HTTPS
    if os.getenv("API_USE_HTTPS", "false").lower() == "true":
        response.headers["Strict-Transport-Security"] = (
            "max-age=31536000; includeSubDomains"
        )

    # Content Security Policy
    response.headers["Content-Security-Policy"] = (
        "default-src 'self'; "
        "script-src 'self' 'unsafe-inline'; "
        "style-src 'self' 'unsafe-inline'; "
        "img-src 'self' data:; "
        "font-src 'self'; "
        "connect-src 'self'"
    )

    return response


# ============================================================================
# Application Lifespan
# ============================================================================


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Application lifespan context manager.
    Handles startup and shutdown events.
    """
    # Startup
    print("Starting Codetoreum API Server...")

    # Print authentication info if auth manager exists
    if hasattr(app.state, "auth_manager"):
        auth_manager: SimpleTokenAuthManager = app.state.auth_manager
        host = os.getenv("API_HOST", "localhost")
        port = int(os.getenv("API_PORT", "8000"))
        use_https = os.getenv("API_USE_HTTPS", "false").lower() == "true"
        auth_manager.print_auth_info(host=host, port=port, use_https=use_https)

    yield

    # Shutdown
    print("Shutting down Codetoreum API Server...")


# ============================================================================
# Application Factory
# ============================================================================


def create_app(
    workflow_command_port: IWorkflowCommandPort,
    task_query_port: ITaskQueryPort,
    config_command_port: IConfigurationCommandPort,
    work_item_command_port: IWorkItemCommandPort,
    work_item_query_port: IWorkItemQueryPort,
    event_bus: IEventBus,
    config_service: IConfigurationService,
    logger: ILogger,
    auth_secret_key: Optional[str] = None,
    disable_auth: bool = False,
    cors_origins: Optional[list] = None,
) -> FastAPI:
    """
    Create and configure FastAPI application.

    Args:
        workflow_command_port: Port for workflow commands
        task_query_port: Port for task queries
        config_command_port: Port for configuration commands
        work_item_command_port: Port for work item commands
        work_item_query_port: Port for work item queries
        event_bus: Event bus for publishing events
        config_service: Configuration service
        logger: Logger instance
        auth_secret_key: Optional secret key for JWT signing. If not provided, one will be generated.
        disable_auth: If True, authentication is disabled (for development/testing only)
        cors_origins: List of allowed CORS origins

    Returns:
        Configured FastAPI application
    """
    # Get configuration from environment
    max_request_size = int(os.getenv("CODETOREUM_MAX_REQUEST_SIZE", str(10 * 1024 * 1024)))  # 10MB default
    rate_limit = os.getenv("CODETOREUM_RATE_LIMIT", "100/minute")

    # Create FastAPI app
    app = FastAPI(
        title="Codetoreum API",
        description=(
            "AI Agent Orchestration Platform API\n\n"
            "Authentication: This API uses a single-token authentication system similar to JupyterLab. "
            "The authentication token is printed to the console on server startup. "
            "Use it in your requests via the Authorization header (Bearer token) or as a query parameter."
        ),
        version="2.0.0",
        docs_url="/api/docs",
        redoc_url="/api/redoc",
        openapi_url="/api/openapi.json",
        lifespan=lifespan,
    )

    # Configure request body size limit
    app.state.max_request_size = max_request_size

    # Create authentication manager (unless disabled)
    auth_manager = None
    auth_deps = None
    if not disable_auth:
        auth_manager = SimpleTokenAuthManager(secret_key=auth_secret_key)
        auth_deps = SimpleAuthDependencies(auth_manager)
        app.state.auth_manager = auth_manager
        app.state.auth_deps = auth_deps

    # Configure rate limiting
    limiter = Limiter(key_func=get_remote_address, default_limits=[rate_limit])
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
    app.add_middleware(SlowAPIMiddleware)

    # Add security headers middleware
    app.add_middleware(BaseHTTPMiddleware, dispatch=security_headers_middleware)

    # Add error handling middleware
    app.add_middleware(BaseHTTPMiddleware, dispatch=error_handling_middleware)

    # Add CORS middleware - use environment variables for production
    if cors_origins is None:
        # Get from environment or use restrictive defaults
        cors_origins_env = os.getenv("CODETOREUM_ALLOWED_ORIGINS", "")
        if cors_origins_env:
            cors_origins = [origin.strip() for origin in cors_origins_env.split(",")]
        else:
            # Development default - allows all origins
            cors_origins = ["*"]

    # In production, be more restrictive with CORS
    allow_all = "*" in cors_origins
    app.add_middleware(
        CORSMiddleware,
        allow_origins=cors_origins,
        allow_credentials=not allow_all,  # Can't use credentials with allow_origins=*
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"] if not allow_all else ["*"],
        allow_headers=["Authorization", "Content-Type"] if not allow_all else ["*"],
    )

    # Create adapters
    webhook_adapter = GitHubWebhookAdapter(
        workflow_command_port=workflow_command_port,
        event_bus=event_bus,
        config_service=config_service,
        logger=logger,
    )

    rest_api_adapter = RestAPIAdapter(
        workflow_command_port=workflow_command_port,
        task_query_port=task_query_port,
        config_command_port=config_command_port,
        auth_dependencies=auth_deps,
    )

    websocket_adapter = WebSocketAdapter()

    # ========================================================================
    # Webhook Endpoints
    # ========================================================================

    @app.post(
        "/webhooks/github",
        tags=["webhooks"],
        summary="Receive GitHub webhook events",
        response_description="Webhook processing result",
    )
    async def github_webhook(
        request: Request,
        x_github_delivery: str = Header(...),
        x_github_event: str = Header(...),
        x_hub_signature_256: str = Header(...),
    ) -> Dict[str, Any]:
        """
        Receives and processes GitHub webhook events.

        This endpoint receives webhook POST requests from GitHub and translates
        them into domain commands for workflow execution.

        **Headers:**
        - X-GitHub-Delivery: Unique delivery ID
        - X-GitHub-Event: Event type (project_card, issues, etc.)
        - X-Hub-Signature-256: HMAC signature for verification

        **Supported Events:**
        - project_card (moved): Card movement between columns
        - issues (opened, edited): New work items
        - issue_comment (created): Agent feedback/questions
        - pull_request (opened, synchronize): Code review triggers
        - discussion (created, answered): Discussion-based workflows

        **Returns:**
        - 202 Accepted: Webhook processed successfully
        - 400 Bad Request: Invalid payload structure
        - 401 Unauthorized: Invalid HMAC signature
        - 404 Not Found: Repository not configured
        - 500 Internal Server Error: Processing failed
        """
        return await webhook_adapter.receive_webhook(
            request=request,
            x_github_delivery=x_github_delivery,
            x_github_event=x_github_event,
            x_hub_signature_256=x_hub_signature_256,
        )

    # ========================================================================
    # REST API Routes
    # ========================================================================

    # Include REST API router
    app.include_router(rest_api_adapter.router)

    # Include Work Items router
    work_items_router = create_work_items_router(
        command_port=work_item_command_port,
        query_port=work_item_query_port,
        auth_deps=auth_deps,
    )
    app.include_router(work_items_router)

    # ========================================================================
    # WebSocket Endpoints
    # ========================================================================

    @app.websocket("/ws/events")
    async def websocket_events(websocket: WebSocket):
        """
        WebSocket endpoint for real-time event streaming.

        Connect to this endpoint to receive real-time updates about
        workflow and execution events.

        **Message Types:**

        Subscribe to events:
        ```json
        {
            "type": "subscribe",
            "subscription_type": "workflow_events",
            "workflow_run_id": "optional-workflow-id",
            "execution_id": "optional-execution-id",
            "project_name": "optional-project-name",
            "event_types": ["optional", "list", "of", "event", "types"]
        }
        ```

        Unsubscribe:
        ```json
        {
            "type": "unsubscribe"
        }
        ```

        Ping (keepalive):
        ```json
        {
            "type": "ping"
        }
        ```

        **Subscription Types:**
        - all_events: Receive all events
        - workflow_events: Receive workflow-related events
        - execution_events: Receive execution-related events
        - logs: Receive log messages
        """
        await websocket_adapter.handle_websocket(websocket)

    # ========================================================================
    # Health Check Endpoints (Unauthenticated)
    # ========================================================================

    @app.get(
        "/api/v2/health",
        tags=["health"],
        summary="Health check endpoint",
        response_model=HealthCheckResponse,
    )
    async def health_check() -> HealthCheckResponse:
        """
        Basic health check endpoint.

        This endpoint does NOT require authentication and can be used for
        monitoring and load balancer health checks.

        Returns:
            Health status
        """
        return HealthCheckResponse(
            status="healthy",
            service="codetoreum-api",
            version="2.0.0",
        )

    @app.get(
        "/api/v2/health/ready",
        tags=["health"],
        summary="Readiness check endpoint",
        response_model=ReadinessCheckResponse,
    )
    async def readiness_check() -> ReadinessCheckResponse:
        """
        Readiness check endpoint.

        Verifies that the service is ready to handle requests.
        This endpoint does NOT require authentication.

        Returns:
            Readiness status
        """
        # TODO: Add checks for dependencies (database, event store, etc.)
        return ReadinessCheckResponse(
            status="ready",
            service="codetoreum-api",
            dependencies={
                "event_bus": "connected",
                "config_service": "connected",
            },
        )

    @app.get(
        "/api/v2/auth/token-info",
        tags=["authentication"],
        summary="Get token information",
        response_model=TokenInfoResponse,
        dependencies=[Depends(auth_deps.require_auth)] if auth_deps else [],
    )
    async def get_token_info() -> TokenInfoResponse:
        """
        Get information about the current authentication token.

        This endpoint requires authentication and returns metadata about
        the token (issuance time, expiration, etc.). Useful for debugging.

        Returns:
            Token information
        """
        if not auth_manager:
            return TokenInfoResponse(
                issued_at="N/A",
                expires_at="N/A",
                subject="N/A",
                is_valid=False,
            )

        info = auth_manager.get_token_info()
        return TokenInfoResponse(**info)

    # ========================================================================
    # Error Handlers
    # ========================================================================

    @app.exception_handler(Exception)
    async def global_exception_handler(request: Request, exc: Exception):
        """Global exception handler for unhandled errors"""
        logger.error(f"Unhandled exception: {exc}")
        return JSONResponse(
            status_code=500,
            content={
                "error": {
                    "type": type(exc).__name__,
                    "message": "Internal server error",
                    "path": str(request.url),
                }
            },
        )

    return app


# ============================================================================
# Application Instance (for development)
# ============================================================================


def create_development_app() -> FastAPI:
    """
    Create FastAPI application with mock dependencies for development.

    Returns:
        FastAPI application with mock dependencies
    """
    import os

    from codetoreum.adapters.primary.github_webhook_adapter import (
        IConfigurationService,
        IEventBus,
        ILogger,
    )
    from codetoreum.ports.input.config_command import (
        IConfigurationCommandPort,
        ConfigurationCommandResult,
    )
    from codetoreum.ports.input.task_query import (
        ITaskQueryPort,
        ExecutionStatusInfo,
        ExecutionStatus,
        ExecutionListResult,
        ExecutionListItem,
        ArtifactListResult,
        ExecutionHistory,
    )
    from codetoreum.ports.input.workflow_command import (
        IWorkflowCommandPort,
        StartWorkflowCommand,
        WorkflowCommandResult,
    )
    from codetoreum.ports.input.work_item_command import (
        IWorkItemCommandPort,
        CreateWorkItemCommand,
        UpdateWorkItemCommand,
        WorkItemCommandResult,
    )
    from codetoreum.ports.input.work_item_query import (
        IWorkItemQueryPort,
        WorkItemFilters,
        PaginationParams as WIPaginationParams,
        WorkItemListResult,
        WorkItemHistory,
    )
    from codetoreum.domain.work_item import WorkItem, WorkItemStatus, WorkItemPriority

    # Mock implementations for development
    class MockWorkflowCommandPort(IWorkflowCommandPort):
        async def start_workflow(
            self, command: StartWorkflowCommand
        ) -> WorkflowCommandResult:
            return WorkflowCommandResult(
                success=True,
                workflow_run_id="mock-workflow-123",
                message="Workflow started (mock)",
                state="STARTED",
            )

        async def pause_workflow(self, command) -> WorkflowCommandResult:
            return WorkflowCommandResult(
                success=True,
                workflow_run_id="mock-workflow-123",
                message="Workflow paused (mock)",
                state="PAUSED",
            )

        async def resume_workflow(self, command) -> WorkflowCommandResult:
            return WorkflowCommandResult(
                success=True,
                workflow_run_id="mock-workflow-123",
                message="Workflow resumed (mock)",
                state="RESUMED",
            )

        async def cancel_workflow(self, command) -> WorkflowCommandResult:
            return WorkflowCommandResult(
                success=True,
                workflow_run_id="mock-workflow-123",
                message="Workflow cancelled (mock)",
                state="CANCELLED",
            )

        async def retry_stage(self, command) -> WorkflowCommandResult:
            return WorkflowCommandResult(
                success=True,
                workflow_run_id="mock-workflow-123",
                message="Stage retried (mock)",
                state="STARTED",
            )

    class MockEventBus(IEventBus):
        async def publish(self, event) -> None:
            print(f"Mock event published: {event}")

    class MockConfigService(IConfigurationService):
        """Mock configuration service for development."""

        async def get_project_config(self, project_id: str):
            from codetoreum.ports.output.config_store import ProjectConfig
            return ProjectConfig(
                id=project_id,
                name="test-project",
                github_org="test-org",
                github_repo="test-repo",
                pipelines=[]
            )

        async def get_project_config_by_name(self, project_name: str):
            from codetoreum.ports.output.config_store import ProjectConfig
            return ProjectConfig(
                id="test-id",
                name=project_name,
                github_org="test-org",
                github_repo="test-repo",
                pipelines=[]
            )

        async def save_project_config(self, config) -> None:
            pass

        async def get_agent_config(self, project_id: str, agent_name: str):
            from codetoreum.ports.output.config_store import AgentConfig
            return AgentConfig(
                project_id=project_id,
                agent_name=agent_name,
                model="claude-3-5-sonnet-20241022",
                timeout=300,
                requires_docker=False,
                makes_code_changes=False
            )

        async def save_agent_config(self, config) -> None:
            pass

        async def get_pipeline_config(self, project_id: str, pipeline_name: str):
            from codetoreum.ports.output.config_store import PipelineConfig
            return PipelineConfig(
                id=f"{project_id}-{pipeline_name}",
                project_id=project_id,
                name=pipeline_name,
                stages=[]
            )

        async def save_pipeline_config(self, config) -> None:
            pass

        async def get_workflow_template(self, template_name: str):
            from codetoreum.ports.output.config_store import WorkflowTemplate
            return WorkflowTemplate(
                id=template_name,
                name=template_name,
                description="Mock workflow template",
                stages=[]
            )

        async def save_workflow_template(self, template) -> None:
            pass

        async def list_projects(self) -> list:
            return []

        async def list_agents(self, project_id: str) -> list:
            return []

        async def list_pipelines(self, project_id: str) -> list:
            return []

        async def search_configs(self, query: str, config_type: Optional[str] = None) -> list:
            return []

        async def get_config_version(self, config_id: str, version: int) -> Dict[str, Any]:
            return {}

        async def list_config_versions(self, config_id: str, limit: int = 10) -> list:
            return []

        async def delete_project_config(self, project_id: str) -> None:
            pass

        async def delete_agent_config(self, project_id: str, agent_name: str) -> None:
            pass

        async def exists(self, project_id: str) -> bool:
            return False

    class MockLogger:
        """Mock logger for development."""

        def __init__(self):
            pass

        def info(self, message: str) -> None:
            print(f"INFO: {message}")

        def warning(self, message: str) -> None:
            print(f"WARNING: {message}")

        def error(self, message: str) -> None:
            print(f"ERROR: {message}")

        def debug(self, message: str) -> None:
            print(f"DEBUG: {message}")

    class MockTaskQueryPort(ITaskQueryPort):
        async def get_execution_status(
            self, execution_id: str
        ) -> ExecutionStatusInfo:
            from datetime import datetime
            return ExecutionStatusInfo(
                execution_id=execution_id,
                workflow_run_id="mock-workflow-123",
                work_item_id="123",
                project_name="test-project",
                pipeline_name="test-pipeline",
                stage_name="test-stage",
                agent_name="test-agent",
                status=ExecutionStatus.COMPLETED,
                started_at=datetime.utcnow(),
                completed_at=datetime.utcnow(),
                duration_seconds=10.5,
            )

        async def list_executions(
            self,
            workflow_run_id=None,
            work_item_id=None,
            project_name=None,
            status=None,
            page=1,
            page_size=50,
        ) -> ExecutionListResult:
            return ExecutionListResult(
                executions=[],
                total_count=0,
                page=page,
                page_size=page_size,
                has_next=False,
            )

        async def get_artifacts(
            self, execution_id: str, artifact_type=None
        ) -> ArtifactListResult:
            return ArtifactListResult(artifacts=[], total_count=0)

        async def get_execution_history(
            self, execution_id: str, limit=None
        ) -> ExecutionHistory:
            return ExecutionHistory(
                execution_id=execution_id, entries=[], total_entries=0
            )

        async def get_workflow_executions(
            self, workflow_run_id: str
        ) -> ExecutionListResult:
            return ExecutionListResult(
                executions=[],
                total_count=0,
                page=1,
                page_size=50,
                has_next=False,
            )

    class MockWorkItemCommandPort(IWorkItemCommandPort):
        """Mock work item command port for development."""

        async def create_work_item(self, command: CreateWorkItemCommand) -> WorkItem:
            from datetime import datetime, timezone
            return WorkItem(
                id="wi-mock-123",
                project_id=command.project_id,
                title=command.title,
                description=command.description,
                status=WorkItemStatus.NEW,
                priority=command.priority,
                labels=command.labels or [],
                external_id=command.external_id,
                external_url=command.external_url,
                assigned_agent_id=None,
                assigned_at=None,
                current_workflow_id=None,
                current_stage=None,
                created_at=datetime.now(timezone.utc),
                updated_at=datetime.now(timezone.utc),
                completed_at=None,
            )

        async def update_work_item(self, command: UpdateWorkItemCommand) -> WorkItem:
            from datetime import datetime, timezone
            return WorkItem(
                id=command.work_item_id,
                project_id="proj-123",
                title=command.title or "Mock Work Item",
                description=command.description or "Mock description",
                status=WorkItemStatus.IN_PROGRESS,
                priority=command.priority or WorkItemPriority.MEDIUM,
                labels=command.labels or [],
                external_id=None,
                external_url=None,
                assigned_agent_id="agent-123",
                assigned_at=datetime.now(timezone.utc),
                current_workflow_id=None,
                current_stage=None,
                created_at=datetime.now(timezone.utc),
                updated_at=datetime.now(timezone.utc),
                completed_at=None,
            )

        async def delete_work_item(self, work_item_id: str) -> WorkItemCommandResult:
            return WorkItemCommandResult(
                success=True,
                work_item_id=work_item_id,
                message="Work item deleted (mock)",
            )

        async def assign_agent(self, command):
            from datetime import datetime, timezone
            return WorkItem(
                id=command.work_item_id,
                project_id="proj-123",
                title="Mock Work Item",
                description="Mock description",
                status=WorkItemStatus.ASSIGNED,
                priority=WorkItemPriority.MEDIUM,
                labels=[],
                external_id=None,
                external_url=None,
                assigned_agent_id=command.agent_id,
                assigned_at=datetime.now(timezone.utc),
                current_workflow_id=None,
                current_stage=None,
                created_at=datetime.now(timezone.utc),
                updated_at=datetime.now(timezone.utc),
                completed_at=None,
            )

        async def update_labels(self, command):
            from datetime import datetime, timezone
            return WorkItem(
                id=command.work_item_id,
                project_id="proj-123",
                title="Mock Work Item",
                description="Mock description",
                status=WorkItemStatus.IN_PROGRESS,
                priority=WorkItemPriority.MEDIUM,
                labels=command.labels,
                external_id=None,
                external_url=None,
                assigned_agent_id="agent-123",
                assigned_at=datetime.now(timezone.utc),
                current_workflow_id=None,
                current_stage=None,
                created_at=datetime.now(timezone.utc),
                updated_at=datetime.now(timezone.utc),
                completed_at=None,
            )

        async def update_priority(self, command):
            from datetime import datetime, timezone
            return WorkItem(
                id=command.work_item_id,
                project_id="proj-123",
                title="Mock Work Item",
                description="Mock description",
                status=WorkItemStatus.IN_PROGRESS,
                priority=command.priority,
                labels=[],
                external_id=None,
                external_url=None,
                assigned_agent_id="agent-123",
                assigned_at=datetime.now(timezone.utc),
                current_workflow_id=None,
                current_stage=None,
                created_at=datetime.now(timezone.utc),
                updated_at=datetime.now(timezone.utc),
                completed_at=None,
            )

        async def attach_workflow(self, command):
            from datetime import datetime, timezone
            return WorkItem(
                id=command.work_item_id,
                project_id="proj-123",
                title="Mock Work Item",
                description="Mock description",
                status=WorkItemStatus.IN_PROGRESS,
                priority=WorkItemPriority.MEDIUM,
                labels=[],
                external_id=None,
                external_url=None,
                assigned_agent_id="agent-123",
                assigned_at=datetime.now(timezone.utc),
                current_workflow_id=command.workflow_id,
                current_stage=None,
                created_at=datetime.now(timezone.utc),
                updated_at=datetime.now(timezone.utc),
                completed_at=None,
            )

        async def update_stage(self, command):
            from datetime import datetime, timezone
            return WorkItem(
                id=command.work_item_id,
                project_id="proj-123",
                title="Mock Work Item",
                description="Mock description",
                status=WorkItemStatus.IN_PROGRESS,
                priority=WorkItemPriority.MEDIUM,
                labels=[],
                external_id=None,
                external_url=None,
                assigned_agent_id="agent-123",
                assigned_at=datetime.now(timezone.utc),
                current_workflow_id="wf-123",
                current_stage=command.stage,
                created_at=datetime.now(timezone.utc),
                updated_at=datetime.now(timezone.utc),
                completed_at=None,
            )

    class MockWorkItemQueryPort(IWorkItemQueryPort):
        """Mock work item query port for development."""

        async def get_work_item(self, work_item_id: str) -> WorkItem:
            from datetime import datetime, timezone
            return WorkItem(
                id=work_item_id,
                project_id="proj-123",
                title="Mock Work Item",
                description="This is a mock work item for development",
                status=WorkItemStatus.IN_PROGRESS,
                priority=WorkItemPriority.MEDIUM,
                labels=["mock", "test"],
                external_id="42",
                external_url="https://github.com/org/repo/issues/42",
                assigned_agent_id="agent-123",
                assigned_at=datetime.now(timezone.utc),
                current_workflow_id="wf-123",
                current_stage="development",
                created_at=datetime.now(timezone.utc),
                updated_at=datetime.now(timezone.utc),
                completed_at=None,
            )

        async def list_work_items(
            self, filters=None, pagination=None
        ) -> WorkItemListResult:
            from datetime import datetime, timezone
            work_item = WorkItem(
                id="wi-mock-123",
                project_id="proj-123",
                title="Mock Work Item 1",
                description="This is a mock work item",
                status=WorkItemStatus.IN_PROGRESS,
                priority=WorkItemPriority.HIGH,
                labels=["mock", "test"],
                external_id="42",
                external_url="https://github.com/org/repo/issues/42",
                assigned_agent_id="agent-123",
                assigned_at=datetime.now(timezone.utc),
                current_workflow_id="wf-123",
                current_stage="development",
                created_at=datetime.now(timezone.utc),
                updated_at=datetime.now(timezone.utc),
                completed_at=None,
            )
            return WorkItemListResult(
                work_items=[work_item],
                total_count=1,
                offset=0,
                limit=20,
                has_next=False,
            )

        async def search_work_items(self, search_params) -> WorkItemListResult:
            return await self.list_work_items()

        async def get_work_item_history(
            self, work_item_id: str, limit=None
        ) -> WorkItemHistory:
            work_item = await self.get_work_item(work_item_id)
            return WorkItemHistory(
                work_item=work_item,
                events=[
                    {
                        "event_type": "WorkItemCreated",
                        "occurred_at": "2025-11-03T09:00:00Z",
                        "payload": {"title": "Mock Work Item"},
                    }
                ],
                total_events=1,
            )

        async def count_work_items(self, filters=None) -> int:
            return 1

    class MockConfigCommandPort(IConfigurationCommandPort):
        async def update_project_config(self, command) -> ConfigurationCommandResult:
            return ConfigurationCommandResult(
                success=True,
                config_version=2,
                message="Config updated (mock)",
                changes_applied=command.updates,
            )

        async def update_agent_config(self, command) -> ConfigurationCommandResult:
            return ConfigurationCommandResult(
                success=True,
                config_version=2,
                message="Agent config updated (mock)",
                changes_applied=command.updates,
            )

        async def update_pipeline_config(self, command) -> ConfigurationCommandResult:
            return ConfigurationCommandResult(
                success=True,
                config_version=2,
                message="Pipeline config updated (mock)",
                changes_applied=command.updates,
            )

        async def add_environment_variable(
            self, command
        ) -> ConfigurationCommandResult:
            return ConfigurationCommandResult(
                success=True,
                config_version=2,
                message="Environment variable added (mock)",
                changes_applied={command.variable_name: command.variable_value},
            )

        async def remove_environment_variable(
            self, command
        ) -> ConfigurationCommandResult:
            return ConfigurationCommandResult(
                success=True,
                config_version=2,
                message="Environment variable removed (mock)",
                changes_applied={},
            )

        async def mount_command(self, command) -> ConfigurationCommandResult:
            return ConfigurationCommandResult(
                success=True,
                config_version=2,
                message="Command mounted (mock)",
                changes_applied={},
            )

        async def unmount_command(self, command) -> ConfigurationCommandResult:
            return ConfigurationCommandResult(
                success=True,
                config_version=2,
                message="Command unmounted (mock)",
                changes_applied={},
            )

        async def mount_subagent(self, command) -> ConfigurationCommandResult:
            return ConfigurationCommandResult(
                success=True,
                config_version=2,
                message="Sub-agent mounted (mock)",
                changes_applied={},
            )

        async def unmount_subagent(self, command) -> ConfigurationCommandResult:
            return ConfigurationCommandResult(
                success=True,
                config_version=2,
                message="Sub-agent unmounted (mock)",
                changes_applied={},
            )

    return create_app(
        workflow_command_port=MockWorkflowCommandPort(),
        task_query_port=MockTaskQueryPort(),
        config_command_port=MockConfigCommandPort(),
        work_item_command_port=MockWorkItemCommandPort(),
        work_item_query_port=MockWorkItemQueryPort(),
        event_bus=MockEventBus(),
        config_service=MockConfigService(),
        logger=MockLogger(),
        auth_secret_key=os.getenv(
            "CODETOREUM_AUTH_SECRET",
            "development-secret-key-change-in-production"
        ),
        disable_auth=os.getenv("CODETOREUM_DISABLE_AUTH", "false").lower() == "true",
        cors_origins=["*"],
    )


# For running with uvicorn
app = create_development_app()
