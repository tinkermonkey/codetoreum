"""
Configuration REST API Router

Provides RESTful endpoints for configuration management (project settings,
environment variables, search, audit trail) without requiring YAML file editing.
"""

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status

from codetoreum.adapters.primary.exception_mapper import map_exception_to_http
from codetoreum.adapters.primary.simple_auth_dependencies import SimpleAuthDependencies
from codetoreum.adapters.primary.config_dtos import (
    AddEnvironmentVariableRequest,
    AgentConfigResponse,
    AgentListResponse,
    ConfigSearchResponse,
    ConfigurationCommandResponse,
    ConfigVersionHistoryResponse,
    PipelineConfigResponse,
    PipelineListResponse,
    ProjectConfigResponse,
    ProjectListResponse,
    SearchConfigsRequest,
    UpdateAgentConfigRequest,
    UpdatePipelineConfigRequest,
    UpdateProjectConfigRequest,
)
from codetoreum.domain.exceptions import DomainError
from codetoreum.ports.exceptions import PortError
from codetoreum.ports.input.exceptions import PortException
from codetoreum.ports.input.config_command import (
    AddEnvironmentVariableCommand,
    IConfigurationCommandPort,
    RemoveEnvironmentVariableCommand,
    UpdateAgentConfigCommand,
    UpdatePipelineConfigCommand,
    UpdateProjectConfigCommand,
)
from codetoreum.ports.input.config_query import (
    IConfigurationQueryPort,
    PaginationParams,
)


def create_config_router(
    command_port: IConfigurationCommandPort,
    query_port: IConfigurationQueryPort,
    auth_deps: Optional[SimpleAuthDependencies] = None,
) -> APIRouter:
    """
    Create the configuration REST API router.

    Args:
        command_port: Configuration command input port
        query_port: Configuration query input port
        auth_deps: Optional authentication dependencies

    Returns:
        Configured APIRouter for configuration management
    """
    # Create router with authentication dependency if provided
    router_kwargs = {
        "prefix": "/api/v2/config",
        "tags": ["configuration"],
    }
    if auth_deps:
        router_kwargs["dependencies"] = [Depends(auth_deps.require_auth)]

    router = APIRouter(**router_kwargs)

    # ========================================================================
    # Project Configuration
    # ========================================================================

    @router.get(
        "/projects/{project_id}",
        response_model=ProjectConfigResponse,
        summary="Get project configuration",
        response_description="Project configuration with masked sensitive values",
    )
    async def get_project_config(
        project_id: str,
    ) -> ProjectConfigResponse:
        """
        Get project configuration by ID.

        **Path Parameters:**
        - project_id: Project ID

        **Returns:**
        - 200 OK: Project configuration (sensitive values masked)
        - 401 Unauthorized: Authentication required
        - 404 Not Found: Project not found

        **Example:**
        ```
        GET /api/v2/config/projects/proj-123
        ```

        **Response:**
        ```json
        {
          "id": "proj-123",
          "name": "my-project",
          "description": "Example project",
          "version": 3,
          "environment_variables": [
            {"name": "API_KEY", "value": "***", "is_secret": true},
            {"name": "DEBUG", "value": "true", "is_secret": false}
          ],
          ...
        }
        ```
        """
        try:
            config = await query_port.get_project_config(
                project_id=project_id,
                include_secrets=False  # Never expose secrets via API
            )

            # TODO(#XX): Sensitive value masking should be delegated to the configuration service.
            # The service should use the is_secret metadata from configuration definitions
            # rather than attempting to infer sensitivity from field names.
            # For now, we assume the backend service handles masking appropriately.

            return ProjectConfigResponse(
                id=config.id,
                name=config.name,
                description=config.description,
                github_org=config.github_org,
                github_repo=config.github_repo,
                version=config.version,
                created_at=config.created_at,
                updated_at=config.updated_at,
                environment_variables=[
                    {
                        "name": k,
                        "value": v,  # Backend service should mask sensitive values
                        "is_secret": False,  # Backend service should provide this metadata
                        "description": None,
                    }
                    for k, v in config.environment_variables.items()
                ],
                mounted_commands=config.mounted_commands,
                mounted_subagents=config.mounted_subagents,
                metadata=config.metadata,
            )

        except (DomainError, PortError, PortException) as e:
            # Map domain, port, and input port exceptions to HTTP exceptions
            raise map_exception_to_http(e)
        except Exception as e:
            # Fallback for unexpected exceptions
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to retrieve project config: {str(e)}",
            )

    @router.put(
        "/projects/{project_id}",
        response_model=ConfigurationCommandResponse,
        summary="Update project configuration",
        response_description="Configuration update result",
    )
    async def update_project_config(
        project_id: str,
        request: UpdateProjectConfigRequest,
    ) -> ConfigurationCommandResponse:
        """
        Update project configuration.

        Updates are applied incrementally - only provided fields are modified.
        Configuration version is incremented and change is recorded in audit trail.

        **Path Parameters:**
        - project_id: Project ID

        **Request Body:**
        - updates: Dictionary of fields to update
        - reason: Optional reason for update (recorded in audit trail)

        **Returns:**
        - 200 OK: Configuration updated successfully
        - 400 Bad Request: Invalid updates
        - 401 Unauthorized: Authentication required
        - 404 Not Found: Project not found

        **Example:**
        ```json
        {
          "updates": {
            "description": "Updated project description",
            "github_org": "my-org"
          },
          "reason": "Correcting GitHub organization name"
        }
        ```

        **Response:**
        ```json
        {
          "success": true,
          "config_version": 4,
          "message": "Project configuration updated",
          "changes_applied": {
            "description": "Updated project description",
            "github_org": "my-org"
          }
        }
        ```
        """
        try:
            # Get project name for command
            config = await query_port.get_project_config(project_id, include_secrets=False)

            # TODO(#XX): Extract user_id from auth context when multi-user authentication is implemented.
            # The SimpleAuthDependencies should be extended to provide user identity information
            # that can be passed to commands for proper audit trail tracking.
            command = UpdateProjectConfigCommand(
                project_name=config.name,
                updates=request.updates,
                user_id="api-user",
                reason=request.reason,
            )

            result = await command_port.update_project_config(command)

            return ConfigurationCommandResponse(
                success=result.success,
                config_version=result.config_version,
                message=result.message,
                changes_applied=result.changes_applied,
                errors=result.errors,
            )

        except (DomainError, PortError, PortException) as e:
            # Map domain, port, and input port exceptions to HTTP exceptions
            raise map_exception_to_http(e)
        except Exception as e:
            # Fallback for unexpected exceptions
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to update project config: {str(e)}",
            )

    @router.get(
        "/projects",
        response_model=ProjectListResponse,
        summary="List all projects",
        response_description="List of projects",
    )
    async def list_projects(
        offset: int = Query(0, ge=0, description="Pagination offset"),
        limit: int = Query(20, ge=1, le=100, description="Pagination limit"),
    ) -> ProjectListResponse:
        """
        List all projects with pagination.

        **Query Parameters:**
        - offset: Pagination offset (default: 0)
        - limit: Pagination limit (default: 20, max: 100)

        **Returns:**
        - 200 OK: List of projects
        - 401 Unauthorized: Authentication required
        """
        try:
            pagination = PaginationParams(offset=offset, limit=limit)
            configs = await query_port.list_projects(pagination=pagination)

            # Convert to response DTOs
            projects = []
            for config in configs:
                projects.append(ProjectConfigResponse(
                    id=config.id,
                    name=config.name,
                    description=config.description,
                    github_org=config.github_org,
                    github_repo=config.github_repo,
                    version=config.version,
                    created_at=config.created_at,
                    updated_at=config.updated_at,
                    environment_variables=[],  # Don't include in list view
                    mounted_commands=[],
                    mounted_subagents=[],
                    metadata=config.metadata,
                ))

            # Get total count
            total = await query_port.count_configs(config_type="project")

            return ProjectListResponse(
                projects=projects,
                total_count=total,
            )

        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to list projects: {str(e)}",
            )

    # ========================================================================
    # Agent Configuration
    # ========================================================================

    @router.get(
        "/projects/{project_id}/agents/{agent_name}",
        response_model=AgentConfigResponse,
        summary="Get agent configuration",
        response_description="Agent configuration",
    )
    async def get_agent_config(
        project_id: str,
        agent_name: str,
    ) -> AgentConfigResponse:
        """
        Get agent configuration.

        **Path Parameters:**
        - project_id: Project ID
        - agent_name: Agent name

        **Returns:**
        - 200 OK: Agent configuration
        - 401 Unauthorized: Authentication required
        - 404 Not Found: Project or agent not found
        """
        try:
            config = await query_port.get_agent_config(
                project_id=project_id,
                agent_name=agent_name
            )

            return AgentConfigResponse(
                project_id=config.project_id,
                agent_name=config.agent_name,
                display_name=config.display_name,
                model=config.model,
                timeout_seconds=config.timeout_seconds,
                max_retries=config.max_retries,
                requires_docker=config.requires_docker,
                requires_dev_container=config.requires_dev_container,
                makes_code_changes=config.makes_code_changes,
                filesystem_write_allowed=config.filesystem_write_allowed,
                version=config.version,
                created_at=config.created_at,
                updated_at=config.updated_at,
                mcp_servers=config.mcp_servers,
                capabilities=config.capabilities,
                metadata=config.metadata,
            )

        except (DomainError, PortError, PortException) as e:
            raise map_exception_to_http(e)
        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to retrieve agent config: {str(e)}",
            )

    @router.put(
        "/projects/{project_id}/agents/{agent_name}",
        response_model=ConfigurationCommandResponse,
        summary="Update agent configuration",
        response_description="Configuration update result",
    )
    async def update_agent_config(
        project_id: str,
        agent_name: str,
        request: UpdateAgentConfigRequest,
    ) -> ConfigurationCommandResponse:
        """
        Update agent configuration.

        **Path Parameters:**
        - project_id: Project ID
        - agent_name: Agent name

        **Request Body:**
        - updates: Dictionary of fields to update
        - reason: Optional reason for update

        **Returns:**
        - 200 OK: Configuration updated
        - 400 Bad Request: Invalid updates
        - 401 Unauthorized: Authentication required
        - 404 Not Found: Agent not found
        """
        try:
            # Get project name
            project_config = await query_port.get_project_config(project_id, include_secrets=False)

            command = UpdateAgentConfigCommand(
                project_name=project_config.name,
                agent_name=agent_name,
                updates=request.updates,
                user_id="api-user",
                reason=request.reason,
            )

            result = await command_port.update_agent_config(command)

            return ConfigurationCommandResponse(
                success=result.success,
                config_version=result.config_version,
                message=result.message,
                changes_applied=result.changes_applied,
                errors=result.errors,
            )

        except (DomainError, PortError, PortException) as e:
            raise map_exception_to_http(e)
        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to update agent config: {str(e)}",
            )

    @router.get(
        "/projects/{project_id}/agents",
        response_model=AgentListResponse,
        summary="List agents for project",
        response_description="List of agent configurations",
    )
    async def list_agents(
        project_id: str,
        offset: int = Query(0, ge=0),
        limit: int = Query(20, ge=1, le=100),
    ) -> AgentListResponse:
        """
        List all agents for a project.

        **Path Parameters:**
        - project_id: Project ID

        **Query Parameters:**
        - offset: Pagination offset
        - limit: Pagination limit

        **Returns:**
        - 200 OK: List of agents
        - 401 Unauthorized: Authentication required
        - 404 Not Found: Project not found
        """
        try:
            pagination = PaginationParams(offset=offset, limit=limit)
            configs = await query_port.list_agents(
                project_id=project_id,
                pagination=pagination
            )

            agents = []
            for config in configs:
                agents.append(AgentConfigResponse(
                    project_id=config.project_id,
                    agent_name=config.agent_name,
                    display_name=config.display_name,
                    model=config.model,
                    timeout_seconds=config.timeout_seconds,
                    max_retries=config.max_retries,
                    requires_docker=config.requires_docker,
                    requires_dev_container=config.requires_dev_container,
                    makes_code_changes=config.makes_code_changes,
                    filesystem_write_allowed=config.filesystem_write_allowed,
                    version=config.version,
                    created_at=config.created_at,
                    updated_at=config.updated_at,
                    mcp_servers=config.mcp_servers,
                    capabilities=config.capabilities,
                    metadata=config.metadata,
                ))

            total = await query_port.count_configs(
                config_type="agent",
                project_id=project_id
            )

            return AgentListResponse(agents=agents, total_count=total)

        except (DomainError, PortError, PortException) as e:
            raise map_exception_to_http(e)
        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to list agents: {str(e)}",
            )

    # ========================================================================
    # Pipeline Configuration
    # ========================================================================

    @router.get(
        "/projects/{project_id}/pipelines/{pipeline_name}",
        response_model=PipelineConfigResponse,
        summary="Get pipeline configuration",
        response_description="Pipeline configuration",
    )
    async def get_pipeline_config(
        project_id: str,
        pipeline_name: str,
    ) -> PipelineConfigResponse:
        """
        Get pipeline configuration.

        **Path Parameters:**
        - project_id: Project ID
        - pipeline_name: Pipeline name

        **Returns:**
        - 200 OK: Pipeline configuration
        - 401 Unauthorized: Authentication required
        - 404 Not Found: Pipeline not found
        """
        try:
            config = await query_port.get_pipeline_config(
                project_id=project_id,
                pipeline_name=pipeline_name
            )

            return PipelineConfigResponse(
                id=config.id,
                project_id=config.project_id,
                name=config.name,
                description=config.description,
                version=config.version,
                stages=config.stages,
                created_at=config.created_at,
                updated_at=config.updated_at,
                metadata=config.metadata,
            )

        except (DomainError, PortError, PortException) as e:
            raise map_exception_to_http(e)
        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to retrieve pipeline config: {str(e)}",
            )

    @router.put(
        "/projects/{project_id}/pipelines/{pipeline_name}",
        response_model=ConfigurationCommandResponse,
        summary="Update pipeline configuration",
        response_description="Configuration update result",
    )
    async def update_pipeline_config(
        project_id: str,
        pipeline_name: str,
        request: UpdatePipelineConfigRequest,
    ) -> ConfigurationCommandResponse:
        """
        Update pipeline configuration.

        **Path Parameters:**
        - project_id: Project ID
        - pipeline_name: Pipeline name

        **Request Body:**
        - updates: Dictionary of fields to update
        - reason: Optional reason for update

        **Returns:**
        - 200 OK: Configuration updated
        - 400 Bad Request: Invalid updates
        - 401 Unauthorized: Authentication required
        - 404 Not Found: Pipeline not found
        """
        try:
            # Get project name
            project_config = await query_port.get_project_config(project_id, include_secrets=False)

            command = UpdatePipelineConfigCommand(
                project_name=project_config.name,
                pipeline_name=pipeline_name,
                updates=request.updates,
                user_id="api-user",
                reason=request.reason,
            )

            result = await command_port.update_pipeline_config(command)

            return ConfigurationCommandResponse(
                success=result.success,
                config_version=result.config_version,
                message=result.message,
                changes_applied=result.changes_applied,
                errors=result.errors,
            )

        except (DomainError, PortError, PortException) as e:
            raise map_exception_to_http(e)
        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to update pipeline config: {str(e)}",
            )

    @router.get(
        "/projects/{project_id}/pipelines",
        response_model=PipelineListResponse,
        summary="List pipelines for project",
        response_description="List of pipeline configurations",
    )
    async def list_pipelines(
        project_id: str,
        offset: int = Query(0, ge=0),
        limit: int = Query(20, ge=1, le=100),
    ) -> PipelineListResponse:
        """
        List all pipelines for a project.

        **Path Parameters:**
        - project_id: Project ID

        **Query Parameters:**
        - offset: Pagination offset
        - limit: Pagination limit

        **Returns:**
        - 200 OK: List of pipelines
        - 401 Unauthorized: Authentication required
        - 404 Not Found: Project not found
        """
        try:
            pagination = PaginationParams(offset=offset, limit=limit)
            configs = await query_port.list_pipelines(
                project_id=project_id,
                pagination=pagination
            )

            pipelines = []
            for config in configs:
                pipelines.append(PipelineConfigResponse(
                    id=config.id,
                    project_id=config.project_id,
                    name=config.name,
                    description=config.description,
                    version=config.version,
                    stages=config.stages,
                    created_at=config.created_at,
                    updated_at=config.updated_at,
                    metadata=config.metadata,
                ))

            total = await query_port.count_configs(
                config_type="pipeline",
                project_id=project_id
            )

            return PipelineListResponse(pipelines=pipelines, total_count=total)

        except (DomainError, PortError, PortException) as e:
            raise map_exception_to_http(e)
        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to list pipelines: {str(e)}",
            )

    # ========================================================================
    # Environment Variables
    # ========================================================================

    @router.post(
        "/projects/{project_id}/env-vars",
        response_model=ConfigurationCommandResponse,
        status_code=status.HTTP_201_CREATED,
        summary="Add or update environment variable",
        response_description="Environment variable added/updated",
    )
    async def add_environment_variable(
        project_id: str,
        request: AddEnvironmentVariableRequest,
    ) -> ConfigurationCommandResponse:
        """
        Add or update an environment variable for a project.

        If the variable already exists, it will be updated.
        Secret variables are encrypted in storage.

        **Path Parameters:**
        - project_id: Project ID

        **Request Body:**
        - variable_name: Variable name (will be uppercased)
        - variable_value: Variable value
        - is_secret: Whether this is a secret (will be encrypted)
        - description: Optional description

        **Returns:**
        - 201 Created: Variable added/updated
        - 400 Bad Request: Invalid variable name or value
        - 401 Unauthorized: Authentication required
        - 404 Not Found: Project not found

        **Example:**
        ```json
        {
          "variable_name": "API_KEY",
          "variable_value": "sk-1234567890",
          "is_secret": true,
          "description": "Third-party API key"
        }
        ```
        """
        try:
            # Get project name
            project_config = await query_port.get_project_config(project_id, include_secrets=False)

            command = AddEnvironmentVariableCommand(
                project_name=project_config.name,
                variable_name=request.variable_name,
                variable_value=request.variable_value,
                user_id="api-user",
                is_secret=request.is_secret,
                description=request.description,
            )

            result = await command_port.add_environment_variable(command)

            return ConfigurationCommandResponse(
                success=result.success,
                config_version=result.config_version,
                message=result.message,
                changes_applied=result.changes_applied,
                errors=result.errors,
            )

        except (DomainError, PortError, PortException) as e:
            raise map_exception_to_http(e)
        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to add environment variable: {str(e)}",
            )

    @router.delete(
        "/projects/{project_id}/env-vars/{variable_name}",
        response_model=ConfigurationCommandResponse,
        summary="Remove environment variable",
        response_description="Environment variable removed",
    )
    async def remove_environment_variable(
        project_id: str,
        variable_name: str,
    ) -> ConfigurationCommandResponse:
        """
        Remove an environment variable from a project.

        **Path Parameters:**
        - project_id: Project ID
        - variable_name: Variable name to remove

        **Returns:**
        - 200 OK: Variable removed
        - 401 Unauthorized: Authentication required
        - 404 Not Found: Project or variable not found
        """
        try:
            # Get project name
            project_config = await query_port.get_project_config(project_id, include_secrets=False)

            command = RemoveEnvironmentVariableCommand(
                project_name=project_config.name,
                variable_name=variable_name.upper(),
                user_id="api-user",
            )

            result = await command_port.remove_environment_variable(command)

            return ConfigurationCommandResponse(
                success=result.success,
                config_version=result.config_version,
                message=result.message,
                changes_applied=result.changes_applied,
                errors=result.errors,
            )

        except (DomainError, PortError, PortException) as e:
            raise map_exception_to_http(e)
        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to remove environment variable: {str(e)}",
            )

    # ========================================================================
    # Configuration Search
    # ========================================================================

    @router.get(
        "/search",
        response_model=ConfigSearchResponse,
        summary="Search configurations",
        response_description="Configuration search results",
    )
    async def search_configs(
        query: str = Query(..., min_length=1, description="Search query string"),
        config_type: Optional[str] = Query(None, description="Filter by type (project, agent, pipeline)"),
        project_id: Optional[str] = Query(None, description="Filter by project"),
        limit: int = Query(20, ge=1, le=100, description="Maximum results"),
    ) -> ConfigSearchResponse:
        """
        Search across all configurations using full-text search.

        Searches across project descriptions, agent names, pipeline definitions, etc.
        Results are ranked by relevance.

        **Query Parameters:**
        - query: Search query string (required)
        - config_type: Optional filter by type (project, agent, pipeline)
        - project_id: Optional filter by project
        - limit: Maximum results to return (default: 20, max: 100)

        **Returns:**
        - 200 OK: Search results with relevance scores
        - 400 Bad Request: Invalid query parameters
        - 401 Unauthorized: Authentication required

        **Examples:**
        - `GET /api/v2/config/search?query=authentication` - Find all configs mentioning auth
        - `GET /api/v2/config/search?query=bug&config_type=workflow` - Find workflows for bugs
        - `GET /api/v2/config/search?query=docker&project_id=proj-123` - Search within project
        """
        try:
            pagination = PaginationParams(offset=0, limit=limit)

            results = await query_port.search_configs(
                query=query,
                config_type=config_type,
                project_id=project_id,
                pagination=pagination,
            )

            return ConfigSearchResponse(
                results=[
                    {
                        "config_id": r.config_id,
                        "config_type": r.config_type,
                        "name": r.name,
                        "description": r.description,
                        "matched_fields": r.matched_fields,
                        "score": r.score,
                    }
                    for r in results.results
                ],
                total_count=results.total_count,
                query=results.query,
                filters=results.filters,
            )

        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Search failed: {str(e)}",
            )

    # ========================================================================
    # Configuration Audit Trail / Version History
    # ========================================================================

    @router.get(
        "/projects/{project_id}/history",
        response_model=ConfigVersionHistoryResponse,
        summary="Get configuration version history",
        response_description="Version history with audit trail",
    )
    async def get_project_config_history(
        project_id: str,
        limit: int = Query(10, ge=1, le=50, description="Maximum versions to return"),
    ) -> ConfigVersionHistoryResponse:
        """
        Get version history for project configuration.

        Returns a list of all configuration changes with timestamps,
        authors, and change descriptions for audit trail purposes.

        **Path Parameters:**
        - project_id: Project ID

        **Query Parameters:**
        - limit: Maximum versions to return (default: 10, max: 50)

        **Returns:**
        - 200 OK: Version history (newest first)
        - 401 Unauthorized: Authentication required
        - 404 Not Found: Project not found

        **Example Response:**
        ```json
        {
          "config_id": "proj-123",
          "config_type": "project",
          "current_version": 5,
          "history": [
            {
              "version": 5,
              "created_at": "2025-11-04T10:30:00Z",
              "created_by": "user@example.com",
              "changes": {"github_org": "new-org"},
              "reason": "Organization renamed"
            },
            ...
          ]
        }
        ```
        """
        try:
            history = await query_port.get_config_version_history(
                config_id=project_id,
                config_type="project",
                limit=limit,
            )

            # Get current version
            config = await query_port.get_project_config(project_id, include_secrets=False)

            return ConfigVersionHistoryResponse(
                config_id=project_id,
                config_type="project",
                current_version=config.version,
                history=[
                    {
                        "version": h.version,
                        "created_at": h.created_at,
                        "created_by": h.created_by,
                        "changes": h.changes,
                        "reason": h.reason,
                    }
                    for h in history
                ],
                total_versions=len(history),
            )

        except (DomainError, PortError, PortException) as e:
            raise map_exception_to_http(e)
        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to retrieve version history: {str(e)}",
            )

    return router
