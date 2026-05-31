"""
REST API Adapter

This module implements the REST API adapter for programmatic access to the
Codetoreum system, providing endpoints for workflow control, task queries,
and configuration management.
"""

from dataclasses import asdict
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Query
from pydantic import BaseModel, Field

from codetoreum.adapters.primary.exception_mapper import map_exception_to_http
from codetoreum.config import (
    SCHEDULER_DEFAULT_PAGE_SIZE,
    SCHEDULER_MAX_PAGE_SIZE,
    WORKSPACE_DEFAULT_PAGE_SIZE,
)
from codetoreum.infrastructure.logging import get_logger
from codetoreum.ports.exceptions import ValidationError
from codetoreum.ports.input.config_command import (
    AddEnvironmentVariableCommand,
    IConfigurationCommandPort,
    RemoveEnvironmentVariableCommand,
    UpdateProjectConfigCommand,
)
from codetoreum.ports.input.config_query import IConfigurationQueryPort
from codetoreum.ports.input.task_query import (
    ExecutionStatus,
    ITaskQueryPort,
)
from codetoreum.ports.input.workflow_command import (
    CancelWorkflowCommand,
    IWorkflowCommandPort,
    PauseWorkflowCommand,
    ResumeWorkflowCommand,
    RetryStageCommand,
    StartWorkflowCommand,
    TriggerType,
)

logger = get_logger(__name__)


# ============================================================================
# Request/Response Models
# ============================================================================


# ---------- Workflow Models ----------


class StartWorkflowRequest(BaseModel):
    """Request to start a new workflow"""

    project_name: str = Field(..., description="Project name")
    work_item_id: str = Field(..., description="Work item ID (issue number, etc.)")
    pipeline_name: str = Field(..., description="Pipeline name to execute")
    stage_name: str | None = Field(None, description="Starting stage (optional)")
    priority: str = Field("MEDIUM", description="Priority: LOW, MEDIUM, HIGH, CRITICAL")
    context: dict[str, Any] | None = Field(None, description="Additional context")


class WorkflowActionRequest(BaseModel):
    """Request to perform an action on a workflow"""

    reason: str | None = Field(None, description="Reason for action")


class RetryStageRequest(BaseModel):
    """Request to retry a failed stage"""

    stage_name: str = Field(..., description="Name of stage to retry")
    reset_state: bool = Field(True, description="Reset previous attempts")


class WorkflowResponse(BaseModel):
    """Response from workflow operations"""

    success: bool
    workflow_run_id: str
    message: str
    state: str
    errors: list[str] | None = None


# ---------- Execution Query Models ----------


class ExecutionStatusResponse(BaseModel):
    """Response with execution status"""

    execution_id: str
    workflow_run_id: str
    work_item_id: str
    project_name: str
    pipeline_name: str
    stage_name: str
    agent_name: str
    status: str
    started_at: datetime | None = None
    completed_at: datetime | None = None
    duration_seconds: float | None = None
    error_message: str | None = None
    retry_count: int = 0
    metadata: dict[str, Any] = Field(default_factory=dict)


class ExecutionListItem(BaseModel):
    """Single execution in list"""

    execution_id: str
    workflow_run_id: str
    work_item_id: str
    stage_name: str
    agent_name: str
    status: str
    started_at: datetime | None = None
    duration_seconds: float | None = None


class ExecutionListResponse(BaseModel):
    """Response with list of executions"""

    executions: list[ExecutionListItem]
    total_count: int
    page: int
    page_size: int
    has_next: bool


class ArtifactInfo(BaseModel):
    """Information about an artifact"""

    artifact_id: str
    execution_id: str
    artifact_type: str
    name: str
    path: str
    size_bytes: int
    created_at: datetime
    mime_type: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class ArtifactListResponse(BaseModel):
    """Response with list of artifacts"""

    artifacts: list[ArtifactInfo]
    total_count: int


# ---------- Configuration Models ----------


class UpdateProjectConfigRequest(BaseModel):
    """Request to update project configuration"""

    updates: dict[str, Any] = Field(..., description="Configuration updates")
    user_id: str = Field(..., description="User making the change")
    reason: str | None = Field(None, description="Reason for change")


class UpdateAgentConfigRequest(BaseModel):
    """Request to update agent configuration"""

    updates: dict[str, Any] = Field(..., description="Agent configuration updates")
    user_id: str = Field(..., description="User making the change")
    reason: str | None = Field(None, description="Reason for change")


class AddEnvironmentVariableRequest(BaseModel):
    """Request to add environment variable"""

    variable_name: str
    variable_value: str
    user_id: str
    is_secret: bool = False
    description: str | None = None


class MountCommandRequest(BaseModel):
    """Request to mount a command"""

    command_name: str
    command_path: str
    user_id: str
    description: str | None = None


class MountSubAgentRequest(BaseModel):
    """Request to mount a sub-agent"""

    subagent_name: str
    subagent_config: dict[str, Any]
    user_id: str
    description: str | None = None


class ConfigurationResponse(BaseModel):
    """Response from configuration operations"""

    success: bool
    config_version: int
    message: str
    changes_applied: dict[str, Any]
    errors: list[str] | None = None


# ============================================================================
# REST API Adapter
# ============================================================================


class RestAPIAdapter:
    """
    REST API adapter providing programmatic access to Codetoreum.

    This adapter exposes workflow control, task queries, and configuration
    management through RESTful HTTP endpoints.
    """

    def __init__(
        self,
        workflow_command_port: IWorkflowCommandPort,
        task_query_port: ITaskQueryPort,
        config_command_port: IConfigurationCommandPort,
        config_query_port: IConfigurationQueryPort,
        auth_dependencies=None,
    ):
        """
        Initialize adapter with ports.

        Args:
            workflow_command_port: Port for workflow commands
            task_query_port: Port for task queries
            config_command_port: Port for configuration commands
            auth_dependencies: Optional authentication dependencies (for protected endpoints)
        """
        self.workflow_port = workflow_command_port
        self.task_port = task_query_port
        self.config_port = config_command_port
        self.config_query_port = config_query_port
        self.auth_dependencies = auth_dependencies

        # Create API router with optional authentication
        # All endpoints in this router will require authentication if auth_dependencies is provided
        router_kwargs: dict[str, Any] = {
            "prefix": "/api/v1",
            "tags": ["api"],
        }
        if auth_dependencies:
            from fastapi import Depends

            router_kwargs["dependencies"] = [Depends(auth_dependencies.require_auth)]

        self.router = APIRouter(**router_kwargs)
        self._register_routes()

    def _register_routes(self):
        """Register all API routes"""

        # ====================================================================
        # Workflow Command Endpoints
        # ====================================================================

        @self.router.post(
            "/workflows",
            response_model=WorkflowResponse,
            summary="Start a new workflow",
            status_code=202,
        )
        async def start_workflow(request: StartWorkflowRequest) -> WorkflowResponse:
            """
            Starts a new workflow execution.

            **Request Body:**
            - project_name: Name of the project
            - work_item_id: Work item identifier (issue number, etc.)
            - pipeline_name: Name of pipeline to execute
            - stage_name: (Optional) Starting stage
            - priority: (Optional) Execution priority
            - context: (Optional) Additional context

            **Returns:**
            - 202 Accepted: Workflow started successfully
            - 400 Bad Request: Invalid parameters
            - 404 Not Found: Project/pipeline not found
            """
            try:
                command = StartWorkflowCommand(
                    project_name=request.project_name,
                    work_item_id=request.work_item_id,
                    pipeline_name=request.pipeline_name,
                    stage_name=request.stage_name,
                    trigger=TriggerType.API,
                    context=request.context,
                    priority=request.priority,
                )

                result = await self.workflow_port.start_workflow(command)

                return WorkflowResponse(
                    success=result.success,
                    workflow_run_id=result.workflow_run_id,
                    message=result.message,
                    state=result.state,
                    errors=result.errors,
                )

            except Exception as e:
                logger.exception("Failed to start workflow", extra={"error": str(e)})
                raise map_exception_to_http(e, "Failed to start workflow")

        @self.router.post(
            "/workflows/{workflow_run_id}/pause",
            response_model=WorkflowResponse,
            summary="Pause a running workflow",
        )
        async def pause_workflow(workflow_run_id: str, request: WorkflowActionRequest) -> WorkflowResponse:
            """
            Pauses an active workflow execution.

            **Parameters:**
            - workflow_run_id: Workflow run identifier

            **Returns:**
            - 200 OK: Workflow paused successfully
            - 404 Not Found: Workflow not found
            - 409 Conflict: Workflow not in pauseable state
            """
            try:
                command = PauseWorkflowCommand(
                    workflow_run_id=workflow_run_id,
                    reason=request.reason or "Paused via API",
                    pause_point="current",
                )

                result = await self.workflow_port.pause_workflow(command)

                return WorkflowResponse(
                    success=result.success,
                    workflow_run_id=result.workflow_run_id,
                    message=result.message,
                    state=result.state,
                    errors=result.errors,
                )

            except Exception as e:
                logger.exception("Failed to pause workflow", extra={"workflow_run_id": workflow_run_id})
                raise map_exception_to_http(e, "Failed to pause workflow")

        @self.router.post(
            "/workflows/{workflow_run_id}/resume",
            response_model=WorkflowResponse,
            summary="Resume a paused workflow",
        )
        async def resume_workflow(workflow_run_id: str, request: WorkflowActionRequest) -> WorkflowResponse:
            """
            Resumes a paused workflow execution.

            **Parameters:**
            - workflow_run_id: Workflow run identifier

            **Returns:**
            - 200 OK: Workflow resumed successfully
            - 404 Not Found: Workflow not found
            - 409 Conflict: Workflow not paused
            """
            try:
                command = ResumeWorkflowCommand(workflow_run_id=workflow_run_id, from_stage=None)

                result = await self.workflow_port.resume_workflow(command)

                return WorkflowResponse(
                    success=result.success,
                    workflow_run_id=result.workflow_run_id,
                    message=result.message,
                    state=result.state,
                    errors=result.errors,
                )

            except Exception as e:
                logger.exception("Failed to resume workflow", extra={"workflow_run_id": workflow_run_id})
                raise map_exception_to_http(e, "Failed to resume workflow")

        @self.router.post(
            "/workflows/{workflow_run_id}/cancel",
            response_model=WorkflowResponse,
            summary="Cancel a workflow",
        )
        async def cancel_workflow(workflow_run_id: str, request: WorkflowActionRequest) -> WorkflowResponse:
            """
            Cancels a workflow execution.

            **Parameters:**
            - workflow_run_id: Workflow run identifier

            **Returns:**
            - 200 OK: Workflow cancelled successfully
            - 404 Not Found: Workflow not found
            """
            try:
                command = CancelWorkflowCommand(
                    workflow_run_id=workflow_run_id,
                    reason=request.reason or "Cancelled via API",
                    force=False,
                )

                result = await self.workflow_port.cancel_workflow(command)

                return WorkflowResponse(
                    success=result.success,
                    workflow_run_id=result.workflow_run_id,
                    message=result.message,
                    state=result.state,
                    errors=result.errors,
                )

            except Exception as e:
                logger.exception("Failed to cancel workflow", extra={"workflow_run_id": workflow_run_id})
                raise map_exception_to_http(e, "Failed to cancel workflow")

        @self.router.post(
            "/workflows/{workflow_run_id}/retry",
            response_model=WorkflowResponse,
            summary="Retry a failed stage",
        )
        async def retry_stage(workflow_run_id: str, request: RetryStageRequest) -> WorkflowResponse:
            """
            Retries a failed workflow stage.

            **Parameters:**
            - workflow_run_id: Workflow run identifier

            **Request Body:**
            - stage_name: Name of stage to retry
            - reset_state: Whether to reset previous attempts

            **Returns:**
            - 200 OK: Stage retry initiated
            - 404 Not Found: Workflow/stage not found
            """
            try:
                command = RetryStageCommand(
                    workflow_run_id=workflow_run_id,
                    stage_name=request.stage_name,
                    reset_state=request.reset_state,
                )

                result = await self.workflow_port.retry_stage(command)

                return WorkflowResponse(
                    success=result.success,
                    workflow_run_id=result.workflow_run_id,
                    message=result.message,
                    state=result.state,
                    errors=result.errors,
                )

            except Exception as e:
                logger.exception(
                    "Failed to retry stage",
                    extra={"workflow_run_id": workflow_run_id, "stage_name": request.stage_name},
                )
                raise map_exception_to_http(e, "Failed to retry stage")

        # ====================================================================
        # Task Query Endpoints
        # ====================================================================

        @self.router.get(
            "/executions",
            response_model=ExecutionListResponse,
            summary="List executions",
        )
        async def list_executions(
            workflow_run_id: str | None = Query(None),
            work_item_id: str | None = Query(None),
            project_name: str | None = Query(None),
            status: str | None = Query(None),
            page: int = Query(1, ge=1),
            page_size: int = Query(SCHEDULER_DEFAULT_PAGE_SIZE, ge=1, le=SCHEDULER_MAX_PAGE_SIZE),
        ) -> ExecutionListResponse:
            """
            Lists executions matching the specified criteria.

            **Query Parameters:**
            - workflow_run_id: Filter by workflow run
            - work_item_id: Filter by work item
            - project_name: Filter by project
            - status: Filter by status (PENDING, RUNNING, COMPLETED, FAILED, etc.)
            - page: Page number (default: 1)
            - page_size: Items per page (default: 50, max: 100)

            **Returns:**
            - 200 OK: List of executions
            """
            try:
                # Parse status if provided
                status_enum = None
                if status:
                    status_enum = ExecutionStatus[status.upper()]

                result = await self.task_port.list_executions(
                    workflow_run_id=workflow_run_id,
                    work_item_id=work_item_id,
                    project_name=project_name,
                    status=status_enum,
                    page=page,
                    page_size=page_size,
                )

                return ExecutionListResponse(
                    executions=[
                        ExecutionListItem(
                            execution_id=e.execution_id,
                            workflow_run_id=e.workflow_run_id,
                            work_item_id=e.work_item_id,
                            stage_name=e.stage_name,
                            agent_name=e.agent_name,
                            status=e.status.value,
                            started_at=e.started_at,
                            duration_seconds=e.duration_seconds,
                        )
                        for e in result.executions
                    ],
                    total_count=result.total_count,
                    page=result.page,
                    page_size=result.page_size,
                    has_next=result.has_next,
                )

            except Exception as e:
                logger.exception("Request failed", extra={"status_code": 400})
                raise map_exception_to_http(e, "Request failed")

        @self.router.get(
            "/executions/{execution_id}",
            response_model=ExecutionStatusResponse,
            summary="Get execution status",
        )
        async def get_execution_status(execution_id: str) -> ExecutionStatusResponse:
            """
            Retrieves detailed status for a specific execution.

            **Parameters:**
            - execution_id: Execution identifier

            **Returns:**
            - 200 OK: Execution status
            - 404 Not Found: Execution not found
            """
            try:
                result = await self.task_port.get_execution_status(execution_id)

                return ExecutionStatusResponse(
                    execution_id=result.execution_id,
                    workflow_run_id=result.workflow_run_id,
                    work_item_id=result.work_item_id,
                    project_name=result.project_name,
                    pipeline_name=result.pipeline_name,
                    stage_name=result.stage_name,
                    agent_name=result.agent_name,
                    status=result.status.value,
                    started_at=result.started_at,
                    completed_at=result.completed_at,
                    duration_seconds=result.duration_seconds,
                    error_message=result.error_message,
                    retry_count=result.retry_count,
                    metadata=result.metadata,
                )

            except Exception as e:
                logger.exception("Request failed", extra={"status_code": 404})
                raise map_exception_to_http(e, "Request failed")

        @self.router.get(
            "/executions/{execution_id}/artifacts",
            response_model=ArtifactListResponse,
            summary="Get execution artifacts",
        )
        async def get_execution_artifacts(
            execution_id: str, artifact_type: str | None = Query(None)
        ) -> ArtifactListResponse:
            """
            Retrieves artifacts produced by an execution.

            **Parameters:**
            - execution_id: Execution identifier
            - artifact_type: (Optional) Filter by artifact type

            **Returns:**
            - 200 OK: List of artifacts
            - 404 Not Found: Execution not found
            """
            try:
                result = await self.task_port.get_artifacts(execution_id, artifact_type=artifact_type)

                return ArtifactListResponse(
                    artifacts=[
                        ArtifactInfo(
                            artifact_id=a.artifact_id,
                            execution_id=a.execution_id,
                            artifact_type=a.artifact_type,
                            name=a.name,
                            path=a.path,
                            size_bytes=a.size_bytes,
                            created_at=a.created_at,
                            mime_type=a.mime_type,
                            metadata=a.metadata,
                        )
                        for a in result.artifacts
                    ],
                    total_count=result.total_count,
                )

            except Exception as e:
                logger.exception("Request failed", extra={"status_code": 404})
                raise map_exception_to_http(e, "Request failed")

        # ====================================================================
        # Configuration Command Endpoints
        # ====================================================================

        @self.router.patch(
            "/configurations/projects/{project_name}",
            response_model=ConfigurationResponse,
            summary="Update project configuration",
        )
        async def update_project_config(
            project_name: str, request: UpdateProjectConfigRequest
        ) -> ConfigurationResponse:
            """
            Updates project configuration.

            **Parameters:**
            - project_name: Project identifier

            **Request Body:**
            - updates: Configuration changes
            - user_id: User making the change
            - reason: (Optional) Reason for change

            **Returns:**
            - 200 OK: Configuration updated
            - 404 Not Found: Project not found
            - 400 Bad Request: Invalid updates
            """
            try:
                command = UpdateProjectConfigCommand(
                    project_name=project_name,
                    updates=request.updates,
                    user_id=request.user_id,
                    reason=request.reason,
                )

                result = await self.config_port.update_project_config(command)

                return ConfigurationResponse(
                    success=result.success,
                    config_version=result.config_version,
                    message=result.message,
                    changes_applied=result.changes_applied,
                    errors=result.errors,
                )

            except Exception as e:
                logger.exception("Request failed", extra={"status_code": 400})
                raise map_exception_to_http(e, "Request failed")

        @self.router.post(
            "/configurations/projects/{project_name}/environment",
            response_model=ConfigurationResponse,
            summary="Add environment variable",
        )
        async def add_environment_variable(
            project_name: str, request: AddEnvironmentVariableRequest
        ) -> ConfigurationResponse:
            """
            Adds or updates an environment variable for a project.

            **Parameters:**
            - project_name: Project identifier

            **Request Body:**
            - variable_name: Name of the variable
            - variable_value: Value of the variable
            - user_id: User making the change
            - is_secret: Whether to encrypt the value
            - description: (Optional) Variable description

            **Returns:**
            - 200 OK: Variable added/updated
            - 404 Not Found: Project not found
            """
            try:
                command = AddEnvironmentVariableCommand(
                    project_name=project_name,
                    variable_name=request.variable_name,
                    variable_value=request.variable_value,
                    user_id=request.user_id,
                    is_secret=request.is_secret,
                    description=request.description,
                )

                result = await self.config_port.add_environment_variable(command)

                return ConfigurationResponse(
                    success=result.success,
                    config_version=result.config_version,
                    message=result.message,
                    changes_applied=result.changes_applied,
                    errors=result.errors,
                )

            except Exception as e:
                logger.exception("Request failed", extra={"status_code": 400})
                raise map_exception_to_http(e, "Request failed")

        @self.router.delete(
            "/configurations/projects/{project_name}/environment/{variable_name}",
            response_model=ConfigurationResponse,
            summary="Remove environment variable",
        )
        async def remove_environment_variable(
            project_name: str, variable_name: str, user_id: str = Query(...)
        ) -> ConfigurationResponse:
            """
            Removes an environment variable from a project.

            **Parameters:**
            - project_name: Project identifier
            - variable_name: Variable to remove
            - user_id: User making the change

            **Returns:**
            - 200 OK: Variable removed
            - 404 Not Found: Project/variable not found
            """
            try:
                command = RemoveEnvironmentVariableCommand(
                    project_name=project_name,
                    variable_name=variable_name,
                    user_id=user_id,
                )

                result = await self.config_port.remove_environment_variable(command)

                return ConfigurationResponse(
                    success=result.success,
                    config_version=result.config_version,
                    message=result.message,
                    changes_applied=result.changes_applied,
                    errors=result.errors,
                )

            except Exception as e:
                logger.exception("Request failed", extra={"status_code": 400})
                raise map_exception_to_http(e, "Request failed")

        # ====================================================================
        # Configuration Query Endpoints (NEW)
        # ====================================================================

        @self.router.get(
            "/configurations/projects/{project_name}",
            response_model=dict[str, Any],
            summary="Get project configuration",
        )
        async def get_project_config(project_name: str) -> dict[str, Any]:
            """
            Retrieves the current configuration for a project.

            **Parameters:**
            - project_name: Project identifier

            **Returns:**
            - 200 OK: Project configuration
            - 404 Not Found: Project not found
            """
            try:
                result = await self.config_query_port.get_project_config_by_name(project_name)
                return asdict(result)
            except Exception as e:
                logger.exception("Request failed", extra={"status_code": 404})
                raise map_exception_to_http(e, "Request failed")

        @self.router.get(
            "/configurations/agents",
            response_model=list[dict[str, Any]],
            summary="List all agent configurations",
        )
        async def list_agent_configs(
            project_name: str | None = Query(None),
        ) -> list[dict[str, Any]]:
            """
            Lists all agent configurations, optionally filtered by project.

            **Query Parameters:**
            - project_name: (Optional) Filter by project

            **Returns:**
            - 200 OK: List of agent configurations
            """
            try:
                # The query port requires a project_id; when none is supplied via the
                # REST query string fall back to listing across all projects by
                # iterating list_projects first.
                if project_name is None:
                    msg = "project_name query parameter is required for listing agent configs"
                    raise ValidationError(msg)
                result = await self.config_query_port.list_agents(project_id=project_name)
                return [asdict(r) for r in result]
            except Exception as e:
                logger.exception("Request failed", extra={"status_code": 400})
                raise map_exception_to_http(e, "Request failed")

        @self.router.get(
            "/configurations/agents/{agent_name}",
            response_model=dict[str, Any],
            summary="Get agent configuration",
        )
        async def get_agent_config(agent_name: str) -> dict[str, Any]:
            """
            Retrieves configuration for a specific agent.

            **Parameters:**
            - agent_name: Agent identifier

            **Returns:**
            - 200 OK: Agent configuration
            - 404 Not Found: Agent not found
            """
            try:
                # Single-agent lookup needs a project_id; this REST surface treats
                # ``agent_name`` as globally unique within an implicit "default" project.
                # Callers that need a richer scope should use the project-scoped query
                # endpoint added in a future API revision.
                result = await self.config_query_port.get_agent_config(
                    project_id="default",
                    agent_name=agent_name,
                )
                return asdict(result)
            except Exception as e:
                logger.exception("Request failed", extra={"status_code": 404})
                raise map_exception_to_http(e, "Request failed")

        @self.router.get(
            "/configurations/pipelines",
            response_model=list[dict[str, Any]],
            summary="List all pipeline configurations",
        )
        async def list_pipeline_configs(
            project_name: str | None = Query(None),
        ) -> list[dict[str, Any]]:
            """
            Lists all pipeline (workflow) configurations, optionally filtered by project.

            **Query Parameters:**
            - project_name: (Optional) Filter by project

            **Returns:**
            - 200 OK: List of pipeline configurations
            """
            try:
                if project_name is None:
                    msg = "project_name query parameter is required for listing pipeline configs"
                    raise ValidationError(msg)
                result = await self.config_query_port.list_pipelines(project_id=project_name)
                return [asdict(r) for r in result]
            except Exception as e:
                logger.exception("Request failed", extra={"status_code": 400})
                raise map_exception_to_http(e, "Request failed")

        @self.router.get(
            "/configurations/pipelines/{pipeline_name}",
            response_model=dict[str, Any],
            summary="Get pipeline configuration",
        )
        async def get_pipeline_config(pipeline_name: str) -> dict[str, Any]:
            """
            Retrieves configuration for a specific pipeline.

            **Parameters:**
            - pipeline_name: Pipeline identifier

            **Returns:**
            - 200 OK: Pipeline configuration
            - 404 Not Found: Pipeline not found
            """
            try:
                result = await self.config_query_port.get_pipeline_config(
                    project_id="default",
                    pipeline_name=pipeline_name,
                )
                return asdict(result)
            except Exception as e:
                logger.exception("Request failed", extra={"status_code": 404})
                raise map_exception_to_http(e, "Request failed")

        @self.router.get(
            "/configurations/history",
            response_model=list[dict[str, Any]],
            summary="Get configuration change history",
        )
        async def get_configuration_history(
            project_name: str | None = Query(None),
            config_type: str | None = Query(None, description="Filter by type: project, agent, pipeline"),
            limit: int = Query(WORKSPACE_DEFAULT_PAGE_SIZE, ge=1, le=500),
            offset: int = Query(0, ge=0),
        ) -> list[dict[str, Any]]:
            """
            Retrieves configuration change history.

            **Query Parameters:**
            - project_name: (Optional) Filter by project
            - config_type: (Optional) Filter by configuration type
            - limit: Maximum number of changes to return (default: 50, max: 500)
            - offset: Number of changes to skip (default: 0)

            **Returns:**
            - 200 OK: List of configuration changes with diffs
            """
            try:
                # The query port surfaces version history per config_id; the REST
                # endpoint exposes a project-scoped aggregate.
                # ``project_name`` is treated as the config_id boundary here.
                if not project_name:
                    msg = "project_name query parameter is required for configuration history"
                    raise ValidationError(msg)
                result = await self.config_query_port.get_config_version_history(
                    config_id=project_name,
                    config_type=config_type or "project",
                    limit=limit,
                )
                return [asdict(r) for r in result]
            except Exception as e:
                logger.exception("Request failed", extra={"status_code": 400})
                raise map_exception_to_http(e, "Request failed")
