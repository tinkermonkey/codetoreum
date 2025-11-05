"""
Agent Configuration Endpoints

Handles CRUD operations for agent configurations.
"""

from fastapi import APIRouter, HTTPException, Query, status

from codetoreum.config import DEFAULT_PAGE_SIZE, MAX_PAGE_SIZE, DEFAULT_OFFSET

from codetoreum.adapters.primary.config_dtos import (
    AgentConfigResponse,
    AgentListResponse,
    ConfigurationCommandResponse,
    UpdateAgentConfigRequest,
)
from codetoreum.adapters.primary.exception_mapper import map_exception_to_http
from codetoreum.domain.exceptions import DomainError
from codetoreum.ports.exceptions import PortError
from codetoreum.ports.input.config_command import (
    IConfigurationCommandPort,
    UpdateAgentConfigCommand,
)
from codetoreum.ports.input.config_query import (
    IConfigurationQueryPort,
    PaginationParams,
)
from codetoreum.ports.input.exceptions import PortException


def register_agent_endpoints(
    router: APIRouter,
    command_port: IConfigurationCommandPort,
    query_port: IConfigurationQueryPort,
) -> None:
    """Register agent configuration endpoints on the router."""

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
        offset: int = Query(DEFAULT_OFFSET, ge=0),
        limit: int = Query(DEFAULT_PAGE_SIZE, ge=1, le=MAX_PAGE_SIZE),
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
