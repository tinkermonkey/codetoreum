"""
Pipeline Configuration Endpoints

Handles CRUD operations for pipeline configurations.
"""

from fastapi import APIRouter, HTTPException, Query, status

from codetoreum.adapters.primary.config_dtos import (
    ConfigurationCommandResponse,
    PipelineConfigResponse,
    PipelineListResponse,
    UpdatePipelineConfigRequest,
)
from codetoreum.adapters.primary.exception_mapper import map_exception_to_http
from codetoreum.config import DEFAULT_OFFSET, DEFAULT_PAGE_SIZE, MAX_PAGE_SIZE
from codetoreum.domain.exceptions import DomainError
from codetoreum.ports.exceptions import PortError
from codetoreum.ports.input.config_command import (
    IConfigurationCommandPort,
    UpdatePipelineConfigCommand,
)
from codetoreum.ports.input.config_query import (
    IConfigurationQueryPort,
    PaginationParams,
)
from codetoreum.ports.input.exceptions import PortException


def register_pipeline_endpoints(
    router: APIRouter,
    command_port: IConfigurationCommandPort,
    query_port: IConfigurationQueryPort,
) -> None:
    """Register pipeline configuration endpoints on the router."""

    @router.get(
        "/pipelines",
        response_model=PipelineListResponse,
        summary="List all pipelines across all projects",
        response_description="List of pipeline configurations",
    )
    async def list_all_pipelines(
        offset: int = Query(DEFAULT_OFFSET, ge=0, description="Pagination offset"),
        limit: int = Query(DEFAULT_PAGE_SIZE, ge=1, le=MAX_PAGE_SIZE, description=f"Pagination limit (max {MAX_PAGE_SIZE})"),
    ) -> PipelineListResponse:
        """
        List all pipelines across all projects with pagination.

        **Query Parameters:**
        - offset: Pagination offset (default: 0)
        - limit: Pagination limit (default: 20, max: 100)

        **Returns:**
        - 200 OK: List of pipelines
        - 401 Unauthorized: Authentication required
        """
        try:
            pagination = PaginationParams(offset=offset, limit=limit)
            configs = await query_port.list_pipelines(
                project_id=None,
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

            total = await query_port.count_configs(config_type="pipeline")

            return PipelineListResponse(pipelines=pipelines, total_count=total)

        except (DomainError, PortError, PortException) as e:
            raise map_exception_to_http(e)
        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to list pipelines: {e!s}",
            )

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
                detail=f"Failed to retrieve pipeline config: {e!s}",
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
                detail=f"Failed to update pipeline config: {e!s}",
            )

    @router.get(
        "/projects/{project_id}/pipelines",
        response_model=PipelineListResponse,
        summary="List pipelines for project",
        response_description="List of pipeline configurations",
    )
    async def list_pipelines(
        project_id: str,
        offset: int = Query(DEFAULT_OFFSET, ge=0),
        limit: int = Query(DEFAULT_PAGE_SIZE, ge=1, le=MAX_PAGE_SIZE),
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
                detail=f"Failed to list pipelines: {e!s}",
            )
