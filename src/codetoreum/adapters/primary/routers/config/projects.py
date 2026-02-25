"""
Project Configuration Endpoints

Handles CRUD operations for project configurations including environment variables.
"""


from fastapi import APIRouter, HTTPException, Query, status

from codetoreum.adapters.primary.config_dtos import (
    ConfigurationCommandResponse,
    ConfigVersionHistoryResponse,
    ProjectConfigResponse,
    ProjectListResponse,
    UpdateProjectConfigRequest,
)
from codetoreum.adapters.primary.exception_mapper import map_exception_to_http
from codetoreum.config import (
    DEFAULT_OFFSET,
    DEFAULT_PAGE_SIZE,
    MAX_PAGE_SIZE,
    VERSIONS_DEFAULT_LIMIT,
    VERSIONS_MAX_LIMIT,
)
from codetoreum.domain.exceptions import DomainError
from codetoreum.ports.exceptions import PortError
from codetoreum.ports.input.config_command import (
    IConfigurationCommandPort,
    UpdateProjectConfigCommand,
)
from codetoreum.ports.input.config_query import (
    IConfigurationQueryPort,
    PaginationParams,
)
from codetoreum.ports.input.exceptions import PortException


def register_project_endpoints(
    router: APIRouter,
    command_port: IConfigurationCommandPort,
    query_port: IConfigurationQueryPort,
) -> None:
    """Register project configuration endpoints on the router."""

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
        """
        try:
            config = await query_port.get_project_config(
                project_id=project_id,
                include_secrets=False  # Never expose secrets via API
            )

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
                        "value": v,
                        "is_secret": False,
                        "description": None,
                    }
                    for k, v in config.environment_variables.items()
                ],
                mounted_commands=config.mounted_commands,
                mounted_subagents=config.mounted_subagents,
                metadata=config.metadata,
            )

        except (DomainError, PortError, PortException) as e:
            raise map_exception_to_http(e)
        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to retrieve project config: {e!s}",
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
        """
        try:
            # Get project name for command
            config = await query_port.get_project_config(project_id, include_secrets=False)

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
            raise map_exception_to_http(e)
        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to update project config: {e!s}",
            )

    @router.get(
        "/projects",
        response_model=ProjectListResponse,
        summary="List all projects",
        response_description="List of projects",
    )
    async def list_projects(
        offset: int = Query(DEFAULT_OFFSET, ge=0, description="Pagination offset"),
        limit: int = Query(DEFAULT_PAGE_SIZE, ge=1, le=MAX_PAGE_SIZE, description=f"Pagination limit (max {MAX_PAGE_SIZE})"),
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
                    environment_variables=[],
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
                detail=f"Failed to list projects: {e!s}",
            )

    @router.get(
        "/projects/{project_id}/history",
        response_model=ConfigVersionHistoryResponse,
        summary="Get configuration version history",
        response_description="Version history with audit trail",
    )
    async def get_project_config_history(
        project_id: str,
        limit: int = Query(VERSIONS_DEFAULT_LIMIT, ge=1, le=VERSIONS_MAX_LIMIT, description=f"Maximum versions to return (max {VERSIONS_MAX_LIMIT})"),
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
                detail=f"Failed to retrieve version history: {e!s}",
            )
