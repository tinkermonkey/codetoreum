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

import asyncio
import logging
import os
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from typing import Any

# Load environment variables from .env file
from dotenv import load_dotenv

load_dotenv()

from fastapi import Depends, FastAPI, Header, Query, Request, Response, WebSocket
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
from codetoreum.adapters.primary.routers.agents import create_agents_router
from codetoreum.adapters.primary.routers.config import create_config_router
from codetoreum.adapters.primary.routers.events import create_events_router
from codetoreum.adapters.primary.routers.executions import create_executions_router
from codetoreum.adapters.primary.routers.metrics import create_metrics_router
from codetoreum.adapters.primary.routers.orchestrator import create_orchestrator_router
from codetoreum.adapters.primary.routers.scheduler import create_scheduler_router
from codetoreum.adapters.primary.routers.work_items import create_work_items_router
from codetoreum.adapters.primary.routers.workflow_runs import (
    create_workflow_runs_router,
)
from codetoreum.adapters.primary.routers.workflows import create_workflows_router
from codetoreum.adapters.primary.routers.workspace import create_workspace_router
from codetoreum.adapters.primary.simple_auth_dependencies import SimpleAuthDependencies
from codetoreum.adapters.primary.websocket_adapter import (
    WebSocketAdapter,
    WebSocketConfig,
)
from codetoreum.config import DEFAULT_API_PORT, DEFAULT_RATE_LIMIT
from codetoreum.infrastructure.auth import SimpleTokenAuthManager
from codetoreum.infrastructure.error_ids import ErrorRegistry

# OpenTelemetry / Signoz integration
from codetoreum.infrastructure.observability.config import ObservabilityConfig
from codetoreum.infrastructure.observability.otel_setup import setup_opentelemetry
from codetoreum.ports.input.agent_command import IAgentCommandPort
from codetoreum.ports.input.agent_query import IAgentQueryPort
from codetoreum.ports.input.config_command import IConfigurationCommandPort
from codetoreum.ports.input.config_query import IConfigurationQueryPort
from codetoreum.ports.input.execution_command import IExecutionCommandPort
from codetoreum.ports.input.execution_query import IExecutionQueryPort
from codetoreum.ports.input.metrics_query import IMetricsQueryPort
from codetoreum.ports.input.orchestration_command import IOrchestrationCommandPort
from codetoreum.ports.input.task_query import ITaskQueryPort
from codetoreum.ports.input.work_item_command import IWorkItemCommandPort
from codetoreum.ports.input.work_item_query import IWorkItemQueryPort
from codetoreum.ports.input.workflow_command import IWorkflowCommandPort
from codetoreum.ports.input.workflow_definition_command import (
    IWorkflowDefinitionCommandPort,
)
from codetoreum.ports.input.workflow_query import IWorkflowQueryPort
from codetoreum.ports.input.workflow_run_query import IWorkflowRunQueryPort
from codetoreum.ports.input.workspace_query import IWorkspaceQueryPort
from codetoreum.ports.output.event_store import IEventStore

logger = logging.getLogger(__name__)


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
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"

    # Content Security Policy - Strict policy for production
    # Note: For development with hot-reload, you may need to add 'unsafe-eval' to script-src
    csp_directives = [
        "default-src 'self'",
        "script-src 'self'",  # Removed 'unsafe-inline' - use nonces or hashes instead
        "style-src 'self'",  # Removed 'unsafe-inline' - use nonces or hashes instead
        "img-src 'self' data: https:",  # Allow HTTPS images and data URIs
        "font-src 'self'",
        "connect-src 'self'",  # WebSocket and API connections
        "frame-ancestors 'none'",  # Equivalent to X-Frame-Options: DENY
        "base-uri 'self'",  # Restrict <base> tag
        "form-action 'self'",  # Restrict form submissions
        "upgrade-insecure-requests",  # Auto-upgrade HTTP to HTTPS
    ]

    # In development, allow unsafe-inline for easier debugging
    if os.getenv("CODETOREUM_ENV", "development").lower() == "development":
        csp_directives[1] = "script-src 'self' 'unsafe-inline' 'unsafe-eval'"
        csp_directives[2] = "style-src 'self' 'unsafe-inline'"

    response.headers["Content-Security-Policy"] = "; ".join(csp_directives)

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
    print("Starting Codetoreum API Server...", flush=True)

    # Note: OpenTelemetry instrumentation is now done at module level
    # (see bottom of this file, after app = create_development_app())

    # Run container recovery on startup if available
    if hasattr(app.state, "container_recovery_service"):
        try:
            logger.info("Starting container recovery process")
            recovery_service = app.state.container_recovery_service
            result = await asyncio.wait_for(
                recovery_service.recover_or_cleanup_containers(),
                timeout=300.0,  # 5 minute timeout
            )
            logger.info(
                f"Container recovery completed: "
                f"{result.recovered} recovered, "
                f"{result.killed} killed, "
                f"{result.errors} errors"
            )
        except TimeoutError:
            logger.error(
                "Container recovery timed out after 5 minutes",
                exc_info=True,
                extra={"error_id": ErrorRegistry.ERR_EXECUTION_TIMEOUT},
            )
        except Exception:
            logger.error(
                "Container recovery failed",
                exc_info=True,
                extra={"error_id": ErrorRegistry.ERR_CONTAINER_ERROR},
            )

    # Print authentication info if auth manager exists
    if hasattr(app.state, "auth_manager"):
        auth_manager: SimpleTokenAuthManager = app.state.auth_manager
        host = os.getenv("API_HOST", "localhost")
        port = int(os.getenv("API_PORT", str(DEFAULT_API_PORT)))
        use_https = os.getenv("API_USE_HTTPS", "false").lower() == "true"
        auth_manager.print_auth_info(host=host, port=port, use_https=use_https)

    yield

    # Shutdown
    print("Shutting down Codetoreum API Server...")

    # Close WebSocket adapter and wait for pending background tasks
    if hasattr(app.state, "websocket_adapter"):
        await app.state.websocket_adapter.close()

    # TODO: Flush pending telemetry data to Signoz before shutdown


# ============================================================================
# Application Factory
# ============================================================================


def create_app(
    workflow_command_port: IWorkflowCommandPort,
    task_query_port: ITaskQueryPort,
    config_command_port: IConfigurationCommandPort,
    config_query_port: IConfigurationQueryPort,
    metrics_query_port: IMetricsQueryPort,
    workspace_query_port: IWorkspaceQueryPort,
    work_item_command_port: IWorkItemCommandPort,
    work_item_query_port: IWorkItemQueryPort,
    workflow_query_port: IWorkflowQueryPort,
    workflow_run_query_port: IWorkflowRunQueryPort,
    workflow_definition_command_port: IWorkflowDefinitionCommandPort,
    orchestration_command_port: IOrchestrationCommandPort,
    agent_command_port: IAgentCommandPort,
    agent_query_port: IAgentQueryPort,
    execution_command_port: IExecutionCommandPort,
    execution_query_port: IExecutionQueryPort,
    event_store: IEventStore,
    event_bus: IEventBus,
    config_service: IConfigurationService,
    logger: ILogger,
    auth_secret_key: str | None = None,
    disable_auth: bool = False,
    cors_origins: list | None = None,
    container_recovery_service: Any | None = None,
) -> FastAPI:
    """
    Create and configure FastAPI application.

    Args:
        workflow_command_port: Port for workflow commands (legacy, for compatibility)
        task_query_port: Port for task queries
        config_command_port: Port for configuration commands
        config_query_port: Port for configuration queries
        metrics_query_port: Port for metrics queries
        workspace_query_port: Port for workspace queries
        work_item_command_port: Port for work item commands
        work_item_query_port: Port for work item queries
        workflow_query_port: Port for workflow definition queries
        workflow_run_query_port: Port for workflow run queries
        workflow_definition_command_port: Port for workflow definition commands
        orchestration_command_port: Port for orchestration commands
        agent_command_port: Port for agent commands
        agent_query_port: Port for agent queries
        execution_command_port: Port for execution commands
        execution_query_port: Port for execution queries
        event_store: Event store for events
        event_bus: Event bus for publishing events
        config_service: Configuration service
        logger: Logger instance
        auth_secret_key: Optional secret key for JWT signing. If not provided, one will be generated.
        disable_auth: If True, authentication is disabled (for development/testing only)
        cors_origins: List of allowed CORS origins
        container_recovery_service: Optional container recovery service for startup recovery

    Returns:
        Configured FastAPI application
    """
    # Get configuration from environment
    max_request_size = int(os.getenv("CODETOREUM_MAX_REQUEST_SIZE", str(10 * 1024 * 1024)))  # 10MB default
    rate_limit = os.getenv("CODETOREUM_RATE_LIMIT", DEFAULT_RATE_LIMIT)

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

    # Store container recovery service if provided
    if container_recovery_service is not None:
        app.state.container_recovery_service = container_recovery_service

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
    # Environment variables:
    #   CODETOREUM_ALLOWED_ORIGINS - Comma-separated list of allowed origins (required in production)
    #   CODETOREUM_ENV - Set to "production" to enable production mode (enforces CORS restrictions)
    # Examples:
    #   CODETOREUM_ALLOWED_ORIGINS="https://app.example.com,https://admin.example.com"
    #   CODETOREUM_ENV="production"
    if cors_origins is None:
        # Get from environment or use restrictive defaults
        cors_origins_env = os.getenv("CODETOREUM_ALLOWED_ORIGINS", "")

        # Check if we're in production mode
        is_production = os.getenv("CODETOREUM_ENV", "development").lower() == "production"

        if cors_origins_env:
            # Parse and validate origins
            origins = [origin.strip() for origin in cors_origins_env.split(",") if origin.strip()]

            # Validate each origin
            validated_origins = []
            for origin in origins:
                # Allow wildcard only in non-production
                if origin == "*":
                    if is_production:
                        msg = (
                            "CORS wildcard (*) is not allowed in production. "
                            "Set CODETOREUM_ALLOWED_ORIGINS to specific origins."
                        )
                        raise ValueError(msg)
                    validated_origins.append(origin)
                else:
                    # Validate origin format (must be http:// or https://)
                    if not (origin.startswith("http://") or origin.startswith("https://")):
                        msg = f"Invalid CORS origin '{origin}'. Must start with http:// or https://"
                        raise ValueError(msg)
                    validated_origins.append(origin)

            cors_origins = validated_origins if validated_origins else ["http://localhost:3000"]
        # No environment variable set
        elif is_production:
            msg = (
                "CODETOREUM_ALLOWED_ORIGINS must be set in production. "
                "Example: CODETOREUM_ALLOWED_ORIGINS=https://app.example.com,https://admin.example.com"
            )
            raise ValueError(msg)
        else:
            # Development default - localhost only
            cors_origins = ["http://localhost:3000", "http://localhost:8000"]

    # In production, be more restrictive with CORS
    allow_all = "*" in cors_origins
    app.add_middleware(
        CORSMiddleware,
        allow_origins=cors_origins,
        allow_credentials=not allow_all,  # Can't use credentials with allow_origins=*, needed for httpOnly cookies
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"] if not allow_all else ["*"],
        allow_headers=["Authorization", "Content-Type"] if not allow_all else ["*"],
        expose_headers=["Set-Cookie"] if not allow_all else ["*"],  # Allow browser to see Set-Cookie header
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

    # Create WebSocket adapter with configuration from environment and auth manager
    websocket_config = WebSocketConfig.from_env()
    websocket_adapter = WebSocketAdapter(
        config=websocket_config,
        auth_manager=auth_manager if not disable_auth else None,
    )
    app.state.websocket_adapter = websocket_adapter

    # Register WebSocket adapter with event bus for real-time streaming
    # Subscribe to all events and broadcast to connected WebSocket clients
    event_bus.subscribe(None, websocket_adapter.broadcast_event)

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
    ) -> dict[str, Any]:
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

    # Include Workflow Runs router (must be registered before Workflows router to
    # prevent /api/v2/workflows/{id} from greedily matching /api/v2/workflows/runs)
    workflow_runs_router = create_workflow_runs_router(
        query_port=workflow_run_query_port,
        auth_deps=auth_deps,
    )
    app.include_router(workflow_runs_router)

    # Include Workflows router
    workflows_router = create_workflows_router(
        definition_command_port=workflow_definition_command_port,
        query_port=workflow_query_port,
        auth_deps=auth_deps,
    )
    app.include_router(workflows_router)

    # Include Orchestrator router
    orchestrator_router = create_orchestrator_router(
        orchestration_command_port=orchestration_command_port,
        auth_deps=auth_deps,
    )
    app.include_router(orchestrator_router)

    # Include Scheduler router
    scheduler_router = create_scheduler_router(
        task_query_port=task_query_port,
        auth_deps=auth_deps,
    )
    app.include_router(scheduler_router)

    # Include Agents router
    agents_router = create_agents_router(
        command_port=agent_command_port,
        query_port=agent_query_port,
        auth_deps=auth_deps,
    )
    app.include_router(agents_router)

    # Include Executions router
    executions_router = create_executions_router(
        command_port=execution_command_port,
        query_port=execution_query_port,
        auth_deps=auth_deps,
    )
    app.include_router(executions_router)

    # Include Configuration router
    config_router = create_config_router(
        command_port=config_command_port,
        query_port=config_query_port,
        auth_deps=auth_deps,
    )
    app.include_router(config_router)

    # Include Metrics router
    metrics_router = create_metrics_router(
        metrics_query_port=metrics_query_port,
        auth_deps=auth_deps,
    )
    app.include_router(metrics_router)

    # Include Events router
    events_router = create_events_router(
        event_store=event_store,
        auth_deps=auth_deps,
    )
    app.include_router(events_router)

    # Include Workspace router
    workspace_router = create_workspace_router(
        query_port=workspace_query_port,
        auth_deps=auth_deps,
    )
    app.include_router(workspace_router)

    # ========================================================================
    # WebSocket Endpoints
    # ========================================================================

    @app.websocket("/api/v2/events/stream")
    async def websocket_events(
        websocket: WebSocket,
        token: str | None = Query(None),
    ):
        """
        WebSocket endpoint for real-time event streaming.

        **Authentication:**
        Provide the authentication token via query parameter: `?token=YOUR_TOKEN`

        **Connection Messages:**

        On successful connection, server sends:
        ```json
        {
            "type": "connected",
            "client_id": "ws-123",
            "message": "Connected to Codetoreum event stream",
            "timestamp": "2025-11-04T10:00:00Z"
        }
        ```

        **Client Message Types:**

        Subscribe to events:
        ```json
        {
            "type": "subscribe",
            "subscription_type": "all_events",
            "event_types": ["ExecutionStarted", "ExecutionCompleted"],
            "work_item_id": "optional",
            "workflow_id": "optional",
            "agent_id": "optional",
            "project_name": "optional"
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

        **Server Message Types:**

        Event message:
        ```json
        {
            "type": "event",
            "event_id": "evt-123",
            "event_type": "ExecutionStarted",
            "data": {...},
            "timestamp": "2025-11-04T10:00:00Z"
        }
        ```

        Flow control warning:
        ```json
        {
            "type": "flow_control",
            "buffer_usage": 0.85,
            "buffer_size": 850,
            "max_buffer_size": 1000,
            "message": "Warning: Buffer at 85% capacity...",
            "timestamp": "2025-11-04T10:00:00Z"
        }
        ```

        **Subscription Types:**
        - `all_events`: Receive all events
        - `workflow_events`: Receive workflow-related events only
        - `execution_events`: Receive execution-related events only

        **Filtering:**
        - `event_types`: List of event types (OR logic)
        - `work_item_id`, `workflow_id`, `agent_id`: Filter by IDs (AND logic)

        **Backpressure Handling:**
        - Buffer limit: 1000 events per client
        - Flow control warning at 80% capacity
        - Automatic disconnection on buffer overflow

        **Heartbeat:**
        - Server sends ping every 30 seconds
        - Client timeout after 90 seconds of inactivity
        """
        await websocket_adapter.handle_websocket(websocket, token=token)

    # Legacy WebSocket endpoint for backward compatibility
    @app.websocket("/ws/events")
    async def websocket_events_legacy(
        websocket: WebSocket,
        token: str | None = Query(None),
    ):
        """Legacy WebSocket endpoint. Use /api/v2/events/stream instead."""
        await websocket_adapter.handle_websocket(websocket, token=token)

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
                subject="simulation-user",
                is_valid=disable_auth,
            )

        info = auth_manager.get_token_info()
        return TokenInfoResponse(**info)

    @app.post(
        "/api/v2/auth/logout",
        tags=["authentication"],
        summary="Logout and clear authentication cookie",
        dependencies=[Depends(auth_deps.require_auth)] if auth_deps else [],
    )
    async def logout(response: Response) -> dict[str, Any]:
        """
        Logout by clearing the httpOnly authentication cookie.

        This endpoint requires authentication and will clear the httpOnly cookie,
        effectively logging the user out. The token itself remains valid until
        expiration, but the browser will no longer send it automatically.

        Returns:
            Success message
        """
        if auth_deps:
            await auth_deps.logout(response)
        return {
            "message": "Logged out successfully",
            "detail": "Authentication cookie has been cleared",
        }

    # ========================================================================
    # Error Handlers
    # ========================================================================

    @app.exception_handler(Exception)
    async def global_exception_handler(request: Request, exc: Exception):
        """Global exception handler for unhandled errors"""
        logger.error(
            f"Unhandled exception: {exc}",
            exc_info=True,
            extra={"error_id": ErrorRegistry.ERR_INTERNAL_ERROR},
        )
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
    )
    from codetoreum.domain.work_item import WorkItem, WorkItemPriority, WorkItemStatus
    from codetoreum.ports.input.config_command import (
        ConfigurationCommandResult,
        IConfigurationCommandPort,
    )
    from codetoreum.ports.input.task_query import (
        ArtifactListResult,
        ExecutionHistory,
        ExecutionListResult,
        ExecutionStatus,
        ExecutionStatusInfo,
        ITaskQueryPort,
    )
    from codetoreum.ports.input.work_item_command import (
        CreateWorkItemCommand,
        IWorkItemCommandPort,
        UpdateWorkItemCommand,
        WorkItemCommandResult,
    )
    from codetoreum.ports.input.work_item_query import (
        IWorkItemQueryPort,
        WorkItemHistory,
        WorkItemListResult,
    )
    from codetoreum.ports.input.workflow_command import (
        IWorkflowCommandPort,
        StartWorkflowCommand,
        WorkflowCommandResult,
    )

    # Mock implementations for development
    class MockWorkflowCommandPort(IWorkflowCommandPort):
        async def start_workflow(self, command: StartWorkflowCommand) -> WorkflowCommandResult:
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
                pipelines=[],
            )

        async def get_project_config_by_name(self, project_name: str):
            from codetoreum.ports.output.config_store import ProjectConfig

            return ProjectConfig(
                id="test-id",
                name=project_name,
                github_org="test-org",
                github_repo="test-repo",
                pipelines=[],
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
                makes_code_changes=False,
            )

        async def save_agent_config(self, config) -> None:
            pass

        async def get_pipeline_config(self, project_id: str, pipeline_name: str):
            from codetoreum.ports.output.config_store import PipelineConfig

            return PipelineConfig(
                id=f"{project_id}-{pipeline_name}",
                project_id=project_id,
                name=pipeline_name,
                stages=[],
            )

        async def save_pipeline_config(self, config) -> None:
            pass

        async def get_workflow_template(self, template_name: str):
            from codetoreum.ports.output.config_store import WorkflowTemplate

            return WorkflowTemplate(
                id=template_name,
                name=template_name,
                description="Mock workflow template",
                stages=[],
            )

        async def save_workflow_template(self, template) -> None:
            pass

        async def list_projects(self) -> list:
            return []

        async def list_agents(self, project_id: str) -> list:
            return []

        async def list_pipelines(self, project_id: str) -> list:
            return []

        async def search_configs(self, query: str, config_type: str | None = None) -> list:
            return []

        async def get_config_version(self, config_id: str, version: int) -> dict[str, Any]:
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
        async def get_execution_status(self, execution_id: str) -> ExecutionStatusInfo:
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
                started_at=datetime.now(UTC),
                completed_at=datetime.now(UTC),
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

        async def get_artifacts(self, execution_id: str, artifact_type=None) -> ArtifactListResult:
            return ArtifactListResult(artifacts=[], total_count=0)

        async def get_execution_history(self, execution_id: str, limit=None) -> ExecutionHistory:
            return ExecutionHistory(execution_id=execution_id, entries=[], total_entries=0)

        async def get_workflow_executions(self, workflow_run_id: str) -> ExecutionListResult:
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
            from datetime import datetime

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
                created_at=datetime.now(UTC),
                updated_at=datetime.now(UTC),
                completed_at=None,
            )

        async def update_work_item(self, command: UpdateWorkItemCommand) -> WorkItem:
            from datetime import datetime

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
                assigned_at=datetime.now(UTC),
                current_workflow_id=None,
                current_stage=None,
                created_at=datetime.now(UTC),
                updated_at=datetime.now(UTC),
                completed_at=None,
            )

        async def delete_work_item(self, work_item_id: str) -> WorkItemCommandResult:
            return WorkItemCommandResult(
                success=True,
                work_item_id=work_item_id,
                message="Work item deleted (mock)",
            )

        async def assign_agent(self, command):
            from datetime import datetime

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
                assigned_at=datetime.now(UTC),
                current_workflow_id=None,
                current_stage=None,
                created_at=datetime.now(UTC),
                updated_at=datetime.now(UTC),
                completed_at=None,
            )

        async def update_labels(self, command):
            from datetime import datetime

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
                assigned_at=datetime.now(UTC),
                current_workflow_id=None,
                current_stage=None,
                created_at=datetime.now(UTC),
                updated_at=datetime.now(UTC),
                completed_at=None,
            )

        async def update_priority(self, command):
            from datetime import datetime

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
                assigned_at=datetime.now(UTC),
                current_workflow_id=None,
                current_stage=None,
                created_at=datetime.now(UTC),
                updated_at=datetime.now(UTC),
                completed_at=None,
            )

        async def attach_workflow(self, command):
            from datetime import datetime

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
                assigned_at=datetime.now(UTC),
                current_workflow_id=command.workflow_id,
                current_stage=None,
                created_at=datetime.now(UTC),
                updated_at=datetime.now(UTC),
                completed_at=None,
            )

        async def update_stage(self, command):
            from datetime import datetime

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
                assigned_at=datetime.now(UTC),
                current_workflow_id="wf-123",
                current_stage=command.stage,
                created_at=datetime.now(UTC),
                updated_at=datetime.now(UTC),
                completed_at=None,
            )

    class MockWorkItemQueryPort(IWorkItemQueryPort):
        """Mock work item query port for development."""

        async def get_work_item(self, work_item_id: str) -> WorkItem:
            from datetime import datetime

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
                assigned_at=datetime.now(UTC),
                current_workflow_id="wf-123",
                current_stage="development",
                created_at=datetime.now(UTC),
                updated_at=datetime.now(UTC),
                completed_at=None,
            )

        async def list_work_items(self, filters=None, pagination=None) -> WorkItemListResult:
            from datetime import datetime

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
                assigned_at=datetime.now(UTC),
                current_workflow_id="wf-123",
                current_stage="development",
                created_at=datetime.now(UTC),
                updated_at=datetime.now(UTC),
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

        async def get_work_item_history(self, work_item_id: str, limit=None) -> WorkItemHistory:
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

        async def add_environment_variable(self, command) -> ConfigurationCommandResult:
            return ConfigurationCommandResult(
                success=True,
                config_version=2,
                message="Environment variable added (mock)",
                changes_applied={command.variable_name: command.variable_value},
            )

        async def remove_environment_variable(self, command) -> ConfigurationCommandResult:
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

    class MockWorkflowRunQueryPort(IWorkflowRunQueryPort):
        """Mock workflow run query port for development."""

        async def get_workflow_run(self, workflow_run_id: str):
            from codetoreum.ports.input.workflow_run_query import (
                WorkflowRunInfo,
                WorkflowRunStageInfo,
                WorkflowRunStatus,
            )

            return WorkflowRunInfo(
                id=workflow_run_id,
                work_item_id="wi-mock-123",
                workflow_id="wf-mock-123",
                project_id="proj-123",
                status=WorkflowRunStatus.RUNNING,
                current_stage_index=1,
                current_stage_name="review",
                stages=[
                    WorkflowRunStageInfo(
                        name="implementation",
                        agent_name="developer_agent",
                        status="completed",
                        started_at=datetime.now(UTC),
                        completed_at=datetime.now(UTC),
                        execution_id="exec-111",
                    ),
                    WorkflowRunStageInfo(
                        name="review",
                        agent_name="reviewer_agent",
                        status="running",
                        started_at=datetime.now(UTC),
                        completed_at=None,
                        execution_id="exec-222",
                    ),
                ],
                started_at=datetime.now(UTC),
                completed_at=None,
                duration=None,
                issue_title="Fix authentication bug",
                issue_number=42,
                project="codetoreum",
                triggered_by="github_webhook",
                priority="high",
                metadata={},
            )

        async def list_workflow_runs(self, filters=None, pagination=None):
            from codetoreum.ports.input.workflow_run_query import (
                WorkflowRunListResult,
                WorkflowRunStatus,
                WorkflowRunSummary,
            )

            return WorkflowRunListResult(
                runs=[
                    WorkflowRunSummary(
                        id="wfrun-mock-123",
                        work_item_id="wi-mock-123",
                        workflow_id="wf-mock-123",
                        project_id="proj-123",
                        status=WorkflowRunStatus.RUNNING,
                        current_stage_index=1,
                        current_stage_name="review",
                        started_at=datetime.now(UTC),
                        completed_at=None,
                        duration=None,
                        issue_title="Fix authentication bug",
                        issue_number=42,
                        project="codetoreum",
                        triggered_by="github_webhook",
                        priority="high",
                    )
                ],
                total_count=1,
                offset=0,
                limit=20,
                has_next=False,
            )

        async def get_workflow_run_events(self, workflow_run_id: str, offset=0, limit=50, event_types=None, since=None):
            from codetoreum.ports.input.workflow_run_query import (
                WorkflowRunEventsResult,
            )

            return WorkflowRunEventsResult(
                events=[
                    {
                        "id": "evt-mock-123",
                        "event_type": "WorkflowStarted",
                        "workflow_run_id": workflow_run_id,
                        "timestamp": datetime.now(UTC),
                        "agent_name": None,
                        "stage_name": "implementation",
                        "status": None,
                        "data": {
                            "work_item_id": "wi-mock-123",
                            "triggered_by": "github_webhook",
                        },
                    }
                ],
                total_count=1,
                offset=offset,
                limit=limit,
                has_next=False,
            )

        async def get_workflow_run_audit(self, workflow_run_id: str, offset=0, limit=100, include_validation=True):
            from codetoreum.ports.input.workflow_run_query import (
                WorkflowRunAuditResult,
                WorkflowRunStatus,
                WorkflowRunSummary,
            )

            # Mock audit response
            return WorkflowRunAuditResult(
                workflow_run=WorkflowRunSummary(
                    id=workflow_run_id,
                    work_item_id="wi-mock-123",
                    workflow_id="wf-mock-123",
                    project_id="proj-123",
                    status=WorkflowRunStatus.COMPLETED,
                    current_stage_index=2,
                    current_stage_name="merge",
                    started_at=datetime.now(UTC),
                    completed_at=datetime.now(UTC),
                    duration=300,
                    issue_title="Mock workflow audit",
                    issue_number=42,
                    project="codetoreum",
                    triggered_by="mock",
                    priority="high",
                ),
                events=[
                    {
                        "id": "evt-1",
                        "event_type": "WorkflowCreated",
                        "aggregate_id": workflow_run_id,
                        "aggregate_type": "Workflow",
                        "timestamp": datetime.now(UTC).isoformat(),
                        "data": {},
                        "correlation_id": None,
                        "causation_id": None,
                        "user_id": None,
                        "metadata": {},
                    }
                ],
                stages=[],
                validation={
                    "sequenceValid": True,
                    "expectedSequence": [],
                    "actualSequence": [],
                    "missingEvents": [],
                    "unexpectedEvents": [],
                    "outOfOrderEvents": [],
                },
                total_count=1,
                offset=offset,
                limit=limit,
                has_next=False,
            )

    class MockWorkflowQueryPort(IWorkflowQueryPort):
        """Mock workflow query port for development."""

        async def get_workflow(self, workflow_id: str, version=None):
            from codetoreum.ports.input.workflow_query import (
                StageInfo,
                WorkflowDefinitionInfo,
            )

            return WorkflowDefinitionInfo(
                id=workflow_id,
                name="mock-workflow",
                description="Mock workflow for development",
                project_id="proj-123",
                version=1,
                stages=[
                    StageInfo(
                        name="development",
                        agent_name="software_engineer",
                        timeout_seconds=1800,
                        retry_count=2,
                        entry_conditions=[],
                        metadata={},
                    )
                ],
                transitions=[],
                work_item_types=["issue"],
                is_template=False,
                is_active=True,
                created_at=datetime.now(UTC),
                updated_at=datetime.now(UTC),
                metadata={},
            )

        async def list_workflows(self, filters=None, pagination=None):
            from codetoreum.ports.input.workflow_query import (
                WorkflowListResult,
                WorkflowSummaryInfo,
            )

            summary = WorkflowSummaryInfo(
                id="wf-mock-123",
                name="mock-workflow",
                description="Mock workflow",
                project_id="proj-123",
                version=1,
                stage_count=1,
                work_item_types=["issue"],
                is_template=False,
                is_active=True,
                created_at=datetime.now(UTC),
                updated_at=datetime.now(UTC),
            )
            return WorkflowListResult(
                workflows=[summary],
                total_count=1,
                offset=0,
                limit=20,
                has_next=False,
            )

        async def get_workflow_versions(self, workflow_id: str, limit=10):
            from codetoreum.ports.input.workflow_query import (
                WorkflowVersionHistoryResult,
                WorkflowVersionInfo,
            )

            return WorkflowVersionHistoryResult(
                workflow_id=workflow_id,
                versions=[
                    WorkflowVersionInfo(
                        version=1,
                        created_at=datetime.now(UTC),
                        created_by=None,
                        changes_summary="Initial version",
                    )
                ],
                total_count=1,
            )

        async def validate_workflow(self, workflow_id: str, version=None):
            from codetoreum.ports.input.workflow_query import WorkflowValidationResult

            return WorkflowValidationResult(
                is_valid=True,
                errors=[],
                warnings=[],
            )

        async def get_workflows_for_work_item_type(self, work_item_type: str, project_id=None):
            return []

        async def count_active_executions(self, workflow_id: str):
            return 0

    class MockWorkflowDefinitionCommandPort(IWorkflowDefinitionCommandPort):
        """Mock workflow definition command port for development."""

        async def create_workflow_definition(self, command):
            from codetoreum.ports.input.workflow_definition_command import (
                WorkflowDefinitionCommandResult,
            )

            return WorkflowDefinitionCommandResult(
                success=True,
                workflow_id="wf-mock-123",
                version=1,
                message="Workflow created (mock)",
            )

        async def update_workflow_definition(self, command):
            from codetoreum.ports.input.workflow_definition_command import (
                WorkflowDefinitionCommandResult,
            )

            return WorkflowDefinitionCommandResult(
                success=True,
                workflow_id=command.workflow_id,
                version=2,
                message="Workflow updated (mock)",
            )

        async def delete_workflow_definition(self, command):
            from codetoreum.ports.input.workflow_definition_command import (
                WorkflowDefinitionCommandResult,
            )

            return WorkflowDefinitionCommandResult(
                success=True,
                workflow_id=command.workflow_id,
                version=None,
                message="Workflow deleted (mock)",
            )

        async def activate_workflow_definition(self, workflow_id: str):
            from codetoreum.ports.input.workflow_definition_command import (
                WorkflowDefinitionCommandResult,
            )

            return WorkflowDefinitionCommandResult(
                success=True,
                workflow_id=workflow_id,
                version=None,
                message="Workflow activated (mock)",
            )

        async def deactivate_workflow_definition(self, workflow_id: str):
            from codetoreum.ports.input.workflow_definition_command import (
                WorkflowDefinitionCommandResult,
            )

            return WorkflowDefinitionCommandResult(
                success=True,
                workflow_id=workflow_id,
                version=None,
                message="Workflow deactivated (mock)",
            )

    class MockOrchestrationCommandPort(IOrchestrationCommandPort):
        """Mock orchestration command port for development."""

        async def start_execution(self, command):
            from codetoreum.ports.input.orchestration_command import (
                OrchestrationCommandResult,
            )

            return OrchestrationCommandResult(
                success=True,
                execution_id="exec-mock-123",
                workflow_run_id="wr-mock-123",
                status="ACCEPTED",
                message="Execution started (mock)",
                started_at=datetime.now(UTC),
            )

        async def cancel_execution(self, command):
            from codetoreum.ports.input.orchestration_command import (
                OrchestrationCommandResult,
            )

            return OrchestrationCommandResult(
                success=True,
                execution_id="exec-mock-123",
                workflow_run_id=command.workflow_run_id,
                status="CANCELLED",
                message="Execution cancelled (mock)",
            )

        async def pause_execution(self, command):
            from codetoreum.ports.input.orchestration_command import (
                OrchestrationCommandResult,
            )

            return OrchestrationCommandResult(
                success=True,
                execution_id="exec-mock-123",
                workflow_run_id=command.workflow_run_id,
                status="PAUSED",
                message="Execution paused (mock)",
            )

        async def resume_execution(self, command):
            from codetoreum.ports.input.orchestration_command import (
                OrchestrationCommandResult,
            )

            return OrchestrationCommandResult(
                success=True,
                execution_id="exec-mock-123",
                workflow_run_id=command.workflow_run_id,
                status="RESUMED",
                message="Execution resumed (mock)",
            )

        async def check_entry_conditions(self, work_item_id: str, workflow_id: str, stage_name=None):
            from codetoreum.ports.input.orchestration_command import (
                EntryConditionCheckResult,
            )

            return EntryConditionCheckResult(
                can_start=True,
                stage_name=stage_name or "development",
                blocking_conditions=[],
                condition_details=[],
            )

    class MockAgentCommandPort(IAgentCommandPort):
        """Mock agent command port for development."""

        async def create_agent(self, command):
            from codetoreum.domain.agent import Agent

            return Agent(
                agent_id="agent-mock-123",
                name=command.name,
                display_name=command.display_name,
                agent_type=command.agent_type,
                role_description=command.role_description,
                model=command.model,
                capabilities=command.capabilities,
            )

        async def update_agent(self, command):
            from codetoreum.domain.agent import Agent, AgentType

            return Agent(
                agent_id=command.agent_id,
                name="mock_agent",
                display_name="Mock Agent",
                agent_type=AgentType.CODE_REVIEWER,
                role_description="Mock agent",
                model="claude-3-sonnet",
                capabilities={},
            )

        async def add_capability(self, command):
            from codetoreum.domain.agent import Agent, AgentType

            return Agent(
                agent_id=command.agent_id,
                name="mock_agent",
                display_name="Mock Agent",
                agent_type=AgentType.CODE_REVIEWER,
                role_description="Mock agent",
                model="claude-3-sonnet",
                capabilities={},
            )

        async def remove_capability(self, command):
            from codetoreum.domain.agent import Agent, AgentType

            return Agent(
                agent_id=command.agent_id,
                name="mock_agent",
                display_name="Mock Agent",
                agent_type=AgentType.CODE_REVIEWER,
                role_description="Mock agent",
                model="claude-3-sonnet",
                capabilities={},
            )

        async def update_capability(self, command):
            from codetoreum.domain.agent import Agent, AgentType

            return Agent(
                agent_id=command.agent_id,
                name="mock_agent",
                display_name="Mock Agent",
                agent_type=AgentType.CODE_REVIEWER,
                role_description="Mock agent",
                model="claude-3-sonnet",
                capabilities={},
            )

        async def add_mcp_server(self, command):
            from codetoreum.domain.agent import Agent, AgentType

            return Agent(
                agent_id=command.agent_id,
                name="mock_agent",
                display_name="Mock Agent",
                agent_type=AgentType.CODE_REVIEWER,
                role_description="Mock agent",
                model="claude-3-sonnet",
                capabilities={},
            )

        async def remove_mcp_server(self, command):
            from codetoreum.domain.agent import Agent, AgentType

            return Agent(
                agent_id=command.agent_id,
                name="mock_agent",
                display_name="Mock Agent",
                agent_type=AgentType.CODE_REVIEWER,
                role_description="Mock agent",
                model="claude-3-sonnet",
                capabilities={},
            )

        async def delete_agent(self, agent_id: str):
            from codetoreum.ports.input.agent_command import AgentCommandResult

            return AgentCommandResult(
                success=True,
                agent_id=agent_id,
                message="Agent deleted (mock)",
                version=1,
            )

    class MockAgentQueryPort(IAgentQueryPort):
        """Mock agent query port for development."""

        async def get_agent(self, agent_id: str, include_stats: bool = False):
            from codetoreum.ports.input.agent_query import AgentInfo

            return AgentInfo(
                id=agent_id,
                name="mock_agent",
                display_name="Mock Agent",
                agent_type="CODE_REVIEWER",
                role_description="Mock agent for testing",
                model="claude-3-sonnet",
                timeout_seconds=300,
                max_retries=3,
                requires_docker=True,
                requires_dev_container=False,
                makes_code_changes=False,
                filesystem_write_allowed=True,
                mcp_servers=[],
                created_at=datetime.now(UTC),
                updated_at=datetime.now(UTC),
                capabilities={},
            )

        async def get_agent_by_name(self, name: str, include_stats: bool = False):
            from codetoreum.ports.input.agent_query import AgentInfo

            return AgentInfo(
                id="agent-mock-123",
                name=name,
                display_name="Mock Agent",
                agent_type="CODE_REVIEWER",
                role_description="Mock agent for testing",
                model="claude-3-sonnet",
                timeout_seconds=300,
                max_retries=3,
                requires_docker=True,
                requires_dev_container=False,
                makes_code_changes=False,
                filesystem_write_allowed=True,
                mcp_servers=[],
                created_at=datetime.now(UTC),
                updated_at=datetime.now(UTC),
                capabilities={},
            )

        async def list_agents(self, filters=None, pagination=None):
            from codetoreum.ports.input.agent_query import AgentInfo, AgentListResult

            return AgentListResult(
                agents=[
                    AgentInfo(
                        id="agent-mock-1",
                        name="mock_agent_1",
                        display_name="Mock Agent 1",
                        agent_type="CODE_REVIEWER",
                        role_description="Mock agent for testing",
                        model="claude-3-sonnet",
                        timeout_seconds=300,
                        max_retries=3,
                        requires_docker=True,
                        requires_dev_container=False,
                        makes_code_changes=False,
                        filesystem_write_allowed=True,
                        mcp_servers=[],
                        created_at=datetime.now(UTC),
                        updated_at=datetime.now(UTC),
                        capabilities={},
                    )
                ],
                total_count=1,
                offset=0,
                limit=20,
                has_next=False,
            )

        async def list_agents_by_capability(self, capability: str, min_proficiency: float = 0.0, pagination=None):
            from codetoreum.ports.input.agent_query import AgentListResult

            return AgentListResult(
                agents=[],
                total_count=0,
                offset=0,
                limit=20,
                has_next=False,
            )

        async def count_agents(self, filters=None):
            return 1

    class MockExecutionCommandPort(IExecutionCommandPort):
        """Mock execution command port for development."""

        async def terminate_execution(self, command):
            from codetoreum.ports.input.execution_command import ExecutionCommandResult

            return ExecutionCommandResult(
                success=True,
                execution_id=command.execution_id,
                message="Execution terminated (mock)",
                new_status="TERMINATED",
            )

        async def pause_execution(self, command):
            from codetoreum.ports.input.execution_command import ExecutionCommandResult

            return ExecutionCommandResult(
                success=True,
                execution_id=command.execution_id,
                message="Execution paused (mock)",
                new_status="PAUSED",
            )

        async def resume_execution(self, command):
            from codetoreum.ports.input.execution_command import ExecutionCommandResult

            return ExecutionCommandResult(
                success=True,
                execution_id=command.execution_id,
                message="Execution resumed (mock)",
                new_status="RUNNING",
            )

    class MockExecutionQueryPort(IExecutionQueryPort):
        """Mock execution query port for development."""

        async def get_execution(self, execution_id: str):
            from codetoreum.domain.agent_execution import ExecutionStatus
            from codetoreum.ports.input.execution_query import ExecutionInfo

            return ExecutionInfo(
                id=execution_id,
                agent_id="agent-mock-123",
                agent_name="mock_agent",
                work_item_id="wi-mock-123",
                workflow_id="wf-mock-123",
                stage_name="development",
                status=ExecutionStatus.RUNNING,
                container_name=None,
                container_id=None,
                output=None,
                error_message=None,
                error_detail=None,
                exit_code=None,
                input_tokens=0,
                output_tokens=0,
                duration_seconds=None,
                initialized_at=datetime.now(UTC),
                started_at=datetime.now(UTC),
                completed_at=None,
            )

        async def list_executions(self, filters=None, pagination=None):
            from codetoreum.domain.agent_execution import ExecutionStatus
            from codetoreum.ports.input.execution_query import (
                ExecutionInfo,
                ExecutionListResult,
            )

            return ExecutionListResult(
                executions=[
                    ExecutionInfo(
                        id="exec-mock-1",
                        agent_id="agent-mock-123",
                        agent_name="mock_agent",
                        work_item_id="wi-mock-123",
                        workflow_id="wf-mock-123",
                        stage_name="development",
                        status=ExecutionStatus.RUNNING,
                        container_name=None,
                        container_id=None,
                        output=None,
                        error_message=None,
                        error_detail=None,
                        exit_code=None,
                        input_tokens=0,
                        output_tokens=0,
                        duration_seconds=None,
                        initialized_at=datetime.now(UTC),
                        started_at=datetime.now(UTC),
                        completed_at=None,
                    )
                ],
                total_count=1,
                offset=0,
                limit=20,
                has_next=False,
            )

        async def get_execution_logs(self, execution_id: str, stage=None, tail=None):
            from codetoreum.ports.input.execution_query import ExecutionLogs

            return ExecutionLogs(
                execution_id=execution_id,
                logs=[],
                total_lines=0,
                stage=stage,
                has_more=False,
            )

        async def get_execution_history(self, execution_id: str, limit=None):
            from codetoreum.ports.input.execution_query import ExecutionHistory

            return ExecutionHistory(
                execution_id=execution_id,
                events=[],
                total_events=0,
            )

        async def count_executions(self, filters=None):
            return 1

    class MockConfigurationQueryPort(IConfigurationQueryPort):
        """Mock configuration query port for development."""

        async def get_project_config(self, project_id: str, include_secrets: bool = False):
            from codetoreum.ports.input.config_query import ProjectConfigInfo

            return ProjectConfigInfo(
                id=project_id,
                name="mock-project",
                description="Mock project for development",
                github_org="mock-org",
                github_repo="mock-repo",
                version=1,
                created_at=datetime.now(UTC),
                updated_at=datetime.now(UTC),
                environment_variables={"DEBUG": "true"},
                mounted_commands=[],
                mounted_subagents=[],
                metadata={},
            )

        async def get_project_config_by_name(self, project_name: str, include_secrets: bool = False):
            return await self.get_project_config("proj-123", include_secrets)

        async def get_agent_config(self, project_id: str, agent_name: str):
            from codetoreum.ports.input.config_query import AgentConfigInfo

            return AgentConfigInfo(
                project_id=project_id,
                agent_name=agent_name,
                display_name="Mock Agent",
                model="claude-3-sonnet",
                timeout_seconds=300,
                max_retries=3,
                requires_docker=True,
                requires_dev_container=False,
                makes_code_changes=False,
                filesystem_write_allowed=True,
                version=1,
                created_at=datetime.now(UTC),
                updated_at=datetime.now(UTC),
                mcp_servers=[],
                capabilities={},
                metadata={},
            )

        async def get_pipeline_config(self, project_id: str, pipeline_name: str):
            from codetoreum.ports.input.config_query import PipelineConfigInfo

            return PipelineConfigInfo(
                id=f"{project_id}-{pipeline_name}",
                project_id=project_id,
                name=pipeline_name,
                description="Mock pipeline",
                version=1,
                stages=[],
                created_at=datetime.now(UTC),
                updated_at=datetime.now(UTC),
                metadata={},
            )

        async def list_projects(self, pagination=None):
            return []

        async def list_agents(self, project_id=None, pagination=None):
            return []

        async def list_pipelines(self, project_id=None, pagination=None):
            return []

        async def search_configs(self, query: str, config_type=None, project_id=None, pagination=None):
            from codetoreum.ports.input.config_query import ConfigSearchResults

            return ConfigSearchResults(results=[], total_count=0, query=query, filters={})

        async def get_config_version_history(self, config_id: str, config_type: str, limit: int = 10):
            return []

        async def get_config_version(self, config_id: str, config_type: str, version: int):
            return {}

        async def count_configs(self, config_type=None, project_id=None):
            return 0

    class MockMetricsQueryPort(IMetricsQueryPort):
        """Mock metrics query port for development."""

        async def get_system_health(self):
            from codetoreum.ports.input.metrics_query import (
                ComponentHealth,
                ComponentHealthInfo,
                SystemHealthInfo,
            )

            return SystemHealthInfo(
                status=ComponentHealth.HEALTHY,
                components=[
                    ComponentHealthInfo(
                        component_name="event_store",
                        status=ComponentHealth.HEALTHY,
                        message="Connected",
                        last_check=datetime.now(UTC),
                        response_time_ms=5.0,
                        details={},
                    )
                ],
                checked_at=datetime.now(UTC),
                uptime_seconds=3600.0,
                version="2.0.0",
            )

        async def get_component_health(self, component_name: str):
            from codetoreum.ports.input.metrics_query import (
                ComponentHealth,
                ComponentHealthInfo,
            )

            return ComponentHealthInfo(
                component_name=component_name,
                status=ComponentHealth.HEALTHY,
                message="OK",
                last_check=datetime.now(UTC),
                response_time_ms=5.0,
                details={},
            )

        async def get_performance_metrics(self, start_time, end_time, aggregation_window_seconds=60):
            from codetoreum.ports.input.metrics_query import PerformanceMetrics

            return PerformanceMetrics(
                api_request_count=100,
                api_error_count=2,
                api_latency_p50_ms=50.0,
                api_latency_p95_ms=150.0,
                api_latency_p99_ms=200.0,
                active_executions=5,
                pending_executions=2,
                completed_executions_total=50,
                failed_executions_total=3,
                avg_execution_duration_seconds=300.0,
                active_containers=5,
                container_cpu_usage_percent=25.0,
                container_memory_usage_mb=512.0,
                queue_depth=2,
                queue_processing_rate=0.5,
                start_time=start_time,
                end_time=end_time,
                aggregation_window_seconds=aggregation_window_seconds,
            )

        async def get_resilience_metrics(self, start_time, end_time):
            from codetoreum.ports.input.metrics_query import ResilienceMetrics

            return ResilienceMetrics(
                circuit_breakers={},
                rate_limiters={},
                retry_attempts_total=10,
                retry_successes_total=8,
                retry_failures_total=2,
                timeout_count=1,
                avg_timeout_duration_ms=5000.0,
                start_time=start_time,
                end_time=end_time,
            )

        async def get_integration_status(self):
            from codetoreum.ports.input.metrics_query import (
                ComponentHealth,
                IntegrationStatus,
            )

            return IntegrationStatus(
                github_connected=True,
                github_api_calls_remaining=5000,
                github_rate_limit_reset=datetime.now(UTC) + timedelta(hours=1),
                github_webhook_health=ComponentHealth.HEALTHY,
                docker_connected=True,
                docker_version="24.0.7",
                docker_containers_running=5,
                event_store_connected=True,
                event_store_latency_ms=5.0,
                config_store_connected=True,
                config_store_latency_ms=3.0,
                checked_at=datetime.now(UTC),
            )

        async def get_simulation_mode_info(self):
            from codetoreum.ports.input.metrics_query import SimulationModeInfo

            return SimulationModeInfo(
                enabled=False,
                time_multiplier=1.0,
                deterministic_responses=False,
                mock_external_services=False,
                event_replay_enabled=False,
                current_simulation_time=None,
                started_at=None,
            )

        async def get_metric_time_series(self, metric_name: str, start_time, end_time, labels=None, aggregation=None):
            from codetoreum.ports.input.metrics_query import MetricTimeSeries

            return MetricTimeSeries(
                metric_name=metric_name,
                data_points=[],
                aggregation=aggregation,
                start_time=start_time,
                end_time=end_time,
            )

        async def list_metric_names(self, prefix=None):
            return ["api.requests", "api.latency", "executions.completed", "executions.failed"]

        async def get_api_endpoint_metrics(self, endpoint_path=None, start_time=None, end_time=None):
            return {"endpoints": {}}

        async def get_agent_execution_metrics(self, agent_name=None, start_time=None, end_time=None):
            return {"agents": {}}

        async def get_active_agents(self):
            """Return mock active agents with proper DTO structure."""
            from codetoreum.adapters.primary.metrics_dtos import ActiveAgentInfo

            return [
                ActiveAgentInfo(
                    execution_id="exec-mock-123",
                    agent_name="developer_agent",
                    work_item_id="wi-mock-456",
                    project="codetoreum",
                    issue_number=42,
                    status="running",
                    started_at=datetime.now(UTC),
                    container_name="claude-code-exec-123",
                ),
                ActiveAgentInfo(
                    execution_id="exec-mock-124",
                    agent_name="reviewer_agent",
                    work_item_id="wi-mock-457",
                    project="codetoreum",
                    issue_number=43,
                    status="running",
                    started_at=datetime.now(UTC) - timedelta(minutes=15),
                    container_name="claude-code-exec-124",
                ),
            ]

        async def get_api_usage(self):
            """Return mock API usage with calculated percentages."""
            from codetoreum.adapters.primary.metrics_dtos import ClaudeApiUsageInfo

            weekly_usage = 15000000
            weekly_quota = 50000000
            session_usage = 2000000
            session_quota = 10000000

            return ClaudeApiUsageInfo(
                available=True,
                weekly_usage=weekly_usage,
                weekly_quota=weekly_quota,
                weekly_usage_percent=round((weekly_usage / weekly_quota) * 100, 1),
                session_usage=session_usage,
                session_quota=session_quota,
                session_usage_percent=round((session_usage / session_quota) * 100, 1),
                session_remaining_minutes=45,
            )

        async def get_repair_cycle_metrics(self, agent_name=None, start_time=None, end_time=None):
            """Return mock repair cycle metrics."""
            return {
                "cycles_started": 10,
                "cycles_completed": 10,
                "cycles_successful": 8,
                "cycles_failed": 2,
                "cycles_fast_failed": 0,
                "durations": [30.0, 45.0, 60.0, 25.0, 35.0, 50.0, 40.0, 55.0, 32.0, 48.0],
                "test_types": {
                    "unit": {"executions": 10, "iterations": 20},
                    "integration": {"executions": 8, "iterations": 15},
                    "e2e": {"executions": 5, "iterations": 10},
                },
                "agents": {
                    "reviewer": {
                        "started": 10,
                        "completed": 10,
                        "successful": 8,
                        "failed": 2,
                        "fast_failed": 0,
                    }
                },
                "files_fixed": {
                    "src/main.py": 1,
                    "src/utils.py": 2,
                    "tests/test_main.py": 1,
                },
                "files_fixed_total": 4,
                "warnings_reviewed_total": 12,
                "avg_duration_seconds": 42.0,
                "avg_agent_calls_per_cycle": 1.5,
            }

    class MockWorkspaceQueryPort(IWorkspaceQueryPort):
        """Mock workspace query port for development."""

        async def get_workspace(self, workspace_id: str):
            from codetoreum.ports.input.workspace_query import (
                ResourceUsage,
                WorkspaceInfo,
                WorkspaceStatus,
            )

            return WorkspaceInfo(
                workspace_id=workspace_id,
                execution_id="exec-123",
                agent_id="agent-456",
                agent_name="mock_agent",
                work_item_id="wi-789",
                project_id="proj-123",
                container_id="container-abc",
                container_name="codetoreum-mock",
                image_name="codetoreum/agent:latest",
                status=WorkspaceStatus.RUNNING,
                resource_usage=ResourceUsage(
                    cpu_percent=25.0,
                    memory_mb=512.0,
                    memory_limit_mb=2048.0,
                    memory_percent=25.0,
                    disk_usage_mb=1024.0,
                    disk_limit_mb=10240.0,
                    network_rx_bytes=1048576,
                    network_tx_bytes=524288,
                ),
                mounted_files=[],
                context_path="/context",
                artifacts_path="/artifacts",
                environment_variables={"DEBUG": "true"},
                working_directory="/workspace",
                created_at=datetime.now(UTC),
                started_at=datetime.now(UTC),
                stopped_at=None,
                last_activity=datetime.now(UTC),
                metadata={},
            )

        async def get_workspace_by_execution(self, execution_id: str):
            return await self.get_workspace(f"ws-{execution_id}")

        async def list_workspaces(self, filters=None, pagination=None):
            from codetoreum.ports.input.workspace_query import WorkspaceListResult

            return WorkspaceListResult(
                workspaces=[],
                total_count=0,
                active_count=0,
                total_cpu_percent=0.0,
                total_memory_mb=0.0,
            )

        async def list_active_workspaces(self, pagination=None):
            return await self.list_workspaces(None, pagination)

        async def get_resource_usage_summary(self, project_id=None):
            return {
                "total_workspaces": 5,
                "active_workspaces": 3,
                "stopped_workspaces": 2,
                "failed_workspaces": 0,
                "total_cpu_percent": 75.0,
                "total_memory_mb": 1536.0,
                "total_disk_mb": 5120.0,
                "avg_cpu_percent": 25.0,
                "avg_memory_mb": 512.0,
            }

        async def count_workspaces(self, filters=None):
            return 5

        async def get_workspace_logs(self, workspace_id: str, tail=None, since=None):
            return ["[Mock] Workspace log line 1", "[Mock] Workspace log line 2"]

    # Create mock event store for development
    from codetoreum.adapters.testing.in_memory_event_store import InMemoryEventStore

    return create_app(
        workflow_command_port=MockWorkflowCommandPort(),
        task_query_port=MockTaskQueryPort(),
        config_command_port=MockConfigCommandPort(),
        config_query_port=MockConfigurationQueryPort(),
        metrics_query_port=MockMetricsQueryPort(),
        workspace_query_port=MockWorkspaceQueryPort(),
        work_item_command_port=MockWorkItemCommandPort(),
        work_item_query_port=MockWorkItemQueryPort(),
        workflow_query_port=MockWorkflowQueryPort(),
        workflow_run_query_port=MockWorkflowRunQueryPort(),
        workflow_definition_command_port=MockWorkflowDefinitionCommandPort(),
        orchestration_command_port=MockOrchestrationCommandPort(),
        agent_command_port=MockAgentCommandPort(),
        agent_query_port=MockAgentQueryPort(),
        execution_command_port=MockExecutionCommandPort(),
        execution_query_port=MockExecutionQueryPort(),
        event_store=InMemoryEventStore(),
        event_bus=MockEventBus(),
        config_service=MockConfigService(),
        logger=MockLogger(),
        auth_secret_key=os.getenv("CODETOREUM_AUTH_SECRET", "development-secret-key-change-in-production"),
        disable_auth=os.getenv("CODETOREUM_DISABLE_AUTH", "false").lower() == "true",
        cors_origins=["*"],
    )


# For running with uvicorn
app = create_development_app()

# Initialize OpenTelemetry instrumentation at module level
# This must happen after app creation but before the app starts handling requests
# Guard prevents double instrumentation if module is imported multiple times
_otel_instrumented = False

if not _otel_instrumented:
    from codetoreum.infrastructure.observability import (
        ObservabilityConfig,
        setup_opentelemetry,
    )

    _otel_config = ObservabilityConfig.from_env()
    if _otel_config.enabled and _otel_config.traces_enabled and _otel_config.signoz.enabled:
        setup_opentelemetry(_otel_config, app)
        print("[MODULE] OpenTelemetry instrumented at module level", flush=True)
        print(f"[MODULE]   → Endpoint: {_otel_config.signoz.grpc_endpoint}", flush=True)
        print(f"[MODULE]   → Service: {_otel_config.signoz.service_name}", flush=True)
        _otel_instrumented = True
    else:
        print("[MODULE] OpenTelemetry disabled or not configured", flush=True)
