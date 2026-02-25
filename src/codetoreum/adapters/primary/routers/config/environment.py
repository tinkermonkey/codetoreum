"""
Environment Variables Endpoints

Handles adding and removing environment variables for projects.
"""

from fastapi import APIRouter, HTTPException, status

from codetoreum.adapters.primary.config_dtos import (
    AddEnvironmentVariableRequest,
    ConfigurationCommandResponse,
)
from codetoreum.adapters.primary.exception_mapper import map_exception_to_http
from codetoreum.domain.exceptions import DomainError
from codetoreum.infrastructure.security import InvalidInputError, validate_env_var_name
from codetoreum.ports.exceptions import PortError
from codetoreum.ports.input.config_command import (
    AddEnvironmentVariableCommand,
    IConfigurationCommandPort,
    RemoveEnvironmentVariableCommand,
)
from codetoreum.ports.input.config_query import IConfigurationQueryPort
from codetoreum.ports.input.exceptions import PortException


def register_environment_endpoints(
    router: APIRouter,
    command_port: IConfigurationCommandPort,
    query_port: IConfigurationQueryPort,
) -> None:
    """Register environment variable endpoints on the router."""

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
                detail=f"Failed to add environment variable: {e!s}",
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
            # Validate variable name from path parameter
            try:
                validated_name = validate_env_var_name(variable_name)
            except InvalidInputError as e:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=str(e)
                )

            # Get project name
            project_config = await query_port.get_project_config(project_id, include_secrets=False)

            command = RemoveEnvironmentVariableCommand(
                project_name=project_config.name,
                variable_name=validated_name,
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
                detail=f"Failed to remove environment variable: {e!s}",
            )
