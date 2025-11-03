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
from codetoreum.infrastructure.auth import SimpleTokenAuthManager
from codetoreum.ports.input.config_command import IConfigurationCommandPort
from codetoreum.ports.input.task_query import ITaskQueryPort
from codetoreum.ports.input.workflow_command import IWorkflowCommandPort


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
        event_bus: Event bus for publishing events
        config_service: Configuration service
        logger: Logger instance
        auth_secret_key: Optional secret key for JWT signing. If not provided, one will be generated.
        disable_auth: If True, authentication is disabled (for development/testing only)
        cors_origins: List of allowed CORS origins

    Returns:
        Configured FastAPI application
    """
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

    # Create authentication manager (unless disabled)
    auth_manager = None
    auth_deps = None
    if not disable_auth:
        auth_manager = SimpleTokenAuthManager(secret_key=auth_secret_key)
        auth_deps = SimpleAuthDependencies(auth_manager)
        app.state.auth_manager = auth_manager
        app.state.auth_deps = auth_deps

    # Add error handling middleware
    app.add_middleware(BaseHTTPMiddleware, dispatch=error_handling_middleware)

    # Add CORS middleware
    if cors_origins is None:
        cors_origins = ["*"]  # Development default

    app.add_middleware(
        CORSMiddleware,
        allow_origins=cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
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
