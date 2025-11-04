"""
Agents REST API Router

Provides RESTful endpoints for agent registry operations including
listing, configuring, and managing agents with capabilities and execution stats.
"""

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status

from codetoreum.adapters.primary.agent_dtos import (
    AddCapabilityRequest,
    AddMcpServerRequest,
    AgentListResponse,
    AgentResponse,
    CreateAgentRequest,
    UpdateAgentRequest,
    UpdateCapabilityRequest,
    AgentCommandResult,
)
from codetoreum.adapters.primary.agent_mappers import AgentMapper
from codetoreum.adapters.primary.simple_auth_dependencies import SimpleAuthDependencies
from codetoreum.domain.agent import AgentType, AgentCapability
from codetoreum.ports.input.agent_command import (
    IAgentCommandPort,
    AddAgentCapabilityCommand,
    RemoveAgentCapabilityCommand,
    UpdateAgentCapabilityCommand,
    AddMcpServerCommand,
    RemoveMcpServerCommand,
)
from codetoreum.ports.input.agent_query import (
    IAgentQueryPort,
    AgentFilters,
    AgentPaginationParams,
    AgentSortField,
    SortOrder,
)


def create_agents_router(
    command_port: IAgentCommandPort,
    query_port: IAgentQueryPort,
    auth_deps: Optional[SimpleAuthDependencies] = None,
) -> APIRouter:
    """
    Create the agents REST API router.

    Args:
        command_port: Agent command input port
        query_port: Agent query input port
        auth_deps: Optional authentication dependencies

    Returns:
        Configured APIRouter for agents
    """
    # Create router with authentication dependency if provided
    router_kwargs = {
        "prefix": "/api/v2/agents",
        "tags": ["agents"],
    }
    if auth_deps:
        router_kwargs["dependencies"] = [Depends(auth_deps.require_auth)]

    router = APIRouter(**router_kwargs)

    # ========================================================================
    # List Agents
    # ========================================================================

    @router.get(
        "",
        response_model=AgentListResponse,
        summary="List agents with filtering and pagination",
        response_description="List of agents in registry",
    )
    async def list_agents(
        capability: Optional[str] = Query(None, description="Filter by capability/skill"),
        agent_type: Optional[str] = Query(None, description="Filter by agent type (maker, reviewer, etc.)"),
        requires_docker: Optional[bool] = Query(None, description="Filter by Docker requirement"),
        makes_code_changes: Optional[bool] = Query(None, description="Filter by code modification capability"),
        offset: int = Query(0, ge=0, description="Offset for pagination"),
        limit: int = Query(20, ge=1, le=100, description="Limit for pagination (max 100)"),
        sort_by: str = Query("updated_at", description="Sort field (name, display_name, agent_type, created_at, updated_at)"),
        sort_order: str = Query("desc", description="Sort order (asc, desc)"),
    ) -> AgentListResponse:
        """
        List agents with optional filtering and pagination.

        **Query Parameters:**
        - capability: Filter by capability/skill name
        - agent_type: Filter by agent type (maker, reviewer, specialized, etc.)
        - requires_docker: Filter by Docker requirement
        - makes_code_changes: Filter by code modification capability
        - offset: Pagination offset (default: 0)
        - limit: Pagination limit (default: 20, max: 100)
        - sort_by: Sort field (name, display_name, agent_type, created_at, updated_at)
        - sort_order: Sort order (asc, desc)

        **Returns:**
        - 200 OK: List of agents with pagination metadata
        - 400 Bad Request: Invalid filter parameters
        - 401 Unauthorized: Authentication required

        **Examples:**
        - List all agents: `GET /api/v2/agents`
        - Filter by capability: `GET /api/v2/agents?capability=code_review`
        - Filter by type: `GET /api/v2/agents?agent_type=maker`
        - Combined filters: `GET /api/v2/agents?makes_code_changes=true&requires_docker=true`
        """
        try:
            # Parse filters
            agent_type_enum = None
            if agent_type:
                try:
                    agent_type_enum = AgentType(agent_type.lower())
                except ValueError:
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail=f"Invalid agent type: {agent_type}",
                    )

            filters = AgentFilters(
                capability=capability,
                agent_type=agent_type_enum,
                requires_docker=requires_docker,
                makes_code_changes=makes_code_changes,
            )

            # Parse pagination
            try:
                sort_field = AgentSortField(sort_by.lower())
            except ValueError:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Invalid sort field: {sort_by}. Must be one of: name, display_name, agent_type, created_at, updated_at",
                )

            try:
                sort_order_enum = SortOrder(sort_order.lower())
            except ValueError:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Invalid sort order: {sort_order}. Must be asc or desc",
                )

            pagination = AgentPaginationParams(
                offset=offset,
                limit=limit,
                sort_by=sort_field,
                sort_order=sort_order_enum,
            )

            # Execute query via port
            result = await query_port.list_agents(filters, pagination)

            # Convert to response DTO
            response = AgentMapper.to_list_response(result)

            # Calculate page number from offset/limit
            response.page = (offset // limit) + 1 if limit > 0 else 1

            return response

        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Failed to list agents: {str(e)}",
            )

    # ========================================================================
    # Get Agent Details
    # ========================================================================

    @router.get(
        "/{agent_id}",
        response_model=AgentResponse,
        summary="Get agent details",
        response_description="Agent details including capabilities and execution statistics",
    )
    async def get_agent(
        agent_id: str,
        include_stats: bool = Query(True, description="Include execution statistics"),
    ) -> AgentResponse:
        """
        Get detailed information about a specific agent.

        **Parameters:**
        - agent_id: Agent ID

        **Query Parameters:**
        - include_stats: Include execution statistics (default: true)

        **Returns:**
        - 200 OK: Agent details with capabilities and optional stats
        - 401 Unauthorized: Authentication required
        - 404 Not Found: Agent not found

        **Response includes:**
        - All agent configuration
        - Capabilities with proficiency levels
        - Container configuration
        - Execution statistics (if include_stats=true)
        - Sensitive environment variable values are masked (e.g., `API_KEY: "***"`)

        **Note:** Sensitive fields like API keys or tokens in metadata are automatically masked.
        """
        try:
            # Get agent info
            agent_info = await query_port.get_agent(agent_id, include_stats=include_stats)

            # Convert to response DTO (mapper handles sensitive field masking)
            response = AgentMapper.to_response(agent_info)

            return response

        except Exception as e:
            if "not found" in str(e).lower():
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"Agent not found: {str(e)}",
                )
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Failed to get agent: {str(e)}",
            )

    # ========================================================================
    # Create Agent
    # ========================================================================

    @router.post(
        "",
        response_model=AgentResponse,
        status_code=status.HTTP_201_CREATED,
        summary="Create a new agent",
        response_description="Created agent",
    )
    async def create_agent(request: CreateAgentRequest) -> AgentResponse:
        """
        Create a new agent definition.

        **Request Body:**
        - name: Agent name/identifier (required, lowercase alphanumeric + underscore)
        - display_name: Human-readable name (required)
        - agent_type: Type of agent (maker, reviewer, specialized, etc.)
        - role_description: Description of agent's role (required)
        - model: LLM model to use (required)
        - capabilities: Dictionary of skills with proficiency levels (required)
        - timeout_seconds: Execution timeout (default: 300, max: 7200)
        - max_retries: Maximum retries (default: 3, max: 10)
        - requires_docker: Docker requirement (default: true)
        - requires_dev_container: Dev container requirement (default: false)
        - makes_code_changes: Whether agent modifies code (default: false)
        - filesystem_write_allowed: Filesystem write permission (default: true)
        - mcp_servers: Optional list of MCP server names

        **Returns:**
        - 201 Created: Agent created successfully
        - 400 Bad Request: Invalid request parameters or agent name already exists
        - 401 Unauthorized: Authentication required

        **Validation:**
        - Agent name must be unique
        - At least one capability required
        - Proficiency levels must be between 0.0 and 1.0
        """
        try:
            # Convert DTO to command
            command = AgentMapper.to_create_command(request)

            # Execute command via port
            agent = await command_port.create_agent(command)

            # Retrieve created agent with stats
            agent_info = await query_port.get_agent(agent.id, include_stats=True)

            # Convert to response DTO
            return AgentMapper.to_response(agent_info)

        except ValueError as e:
            # Invalid enum values or validation errors
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid request: {str(e)}",
            )
        except Exception as e:
            # Domain errors (agent already exists, etc.)
            if "already exists" in str(e).lower():
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Agent with name '{request.name}' already exists",
                )
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Failed to create agent: {str(e)}",
            )

    # ========================================================================
    # Update Agent
    # ========================================================================

    @router.put(
        "/{agent_id}",
        response_model=AgentResponse,
        summary="Update agent configuration",
        response_description="Updated agent",
    )
    async def update_agent(
        agent_id: str,
        request: UpdateAgentRequest,
    ) -> AgentResponse:
        """
        Update an existing agent's configuration.

        **Parameters:**
        - agent_id: Agent ID

        **Request Body:**
        - display_name: Updated display name (optional)
        - role_description: Updated role description (optional)
        - model: Updated LLM model (optional)
        - timeout_seconds: Updated timeout (optional, max: 7200)
        - max_retries: Updated max retries (optional, max: 10)
        - requires_docker: Updated Docker requirement (optional)
        - requires_dev_container: Updated dev container requirement (optional)
        - makes_code_changes: Updated code changes flag (optional)
        - filesystem_write_allowed: Updated filesystem write permission (optional)

        **Returns:**
        - 200 OK: Agent updated successfully
        - 400 Bad Request: Invalid request parameters
        - 401 Unauthorized: Authentication required
        - 404 Not Found: Agent not found

        **Note:**
        - Only provided fields will be updated
        - Emits domain event for audit trail
        - Increments agent version
        """
        try:
            # Convert DTO to command
            command = AgentMapper.to_update_command(agent_id, request)

            # Execute command via port
            agent = await command_port.update_agent(command)

            # Retrieve updated agent with stats
            agent_info = await query_port.get_agent(agent.id, include_stats=True)

            # Convert to response DTO
            return AgentMapper.to_response(agent_info)

        except ValueError as e:
            # Invalid enum values or validation errors
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid request: {str(e)}",
            )
        except Exception as e:
            # Domain errors
            if "not found" in str(e).lower():
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"Agent not found: {str(e)}",
                )
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Failed to update agent: {str(e)}",
            )

    # ========================================================================
    # Capability Management
    # ========================================================================

    @router.post(
        "/{agent_id}/capabilities",
        response_model=AgentResponse,
        summary="Add capability to agent",
        response_description="Updated agent with new capability",
    )
    async def add_capability(
        agent_id: str,
        request: AddCapabilityRequest,
    ) -> AgentResponse:
        """
        Add a new capability to an agent.

        **Parameters:**
        - agent_id: Agent ID

        **Request Body:**
        - capability: Capability to add (skill, proficiency, description)

        **Returns:**
        - 200 OK: Capability added successfully
        - 400 Bad Request: Capability already exists or invalid proficiency
        - 401 Unauthorized: Authentication required
        - 404 Not Found: Agent not found
        """
        try:
            # Convert DTO to domain model
            capability = AgentCapability(
                skill=request.capability.skill,
                proficiency=request.capability.proficiency,
                description=request.capability.description,
            )

            command = AddAgentCapabilityCommand(
                agent_id=agent_id,
                capability=capability,
            )

            # Execute command via port
            agent = await command_port.add_capability(command)

            # Retrieve updated agent
            agent_info = await query_port.get_agent(agent.id, include_stats=True)

            return AgentMapper.to_response(agent_info)

        except Exception as e:
            if "not found" in str(e).lower():
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"Agent not found: {str(e)}",
                )
            elif "already" in str(e).lower():
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Capability already exists: {str(e)}",
                )
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Failed to add capability: {str(e)}",
            )

    @router.delete(
        "/{agent_id}/capabilities/{skill}",
        response_model=AgentResponse,
        summary="Remove capability from agent",
        response_description="Updated agent without removed capability",
    )
    async def remove_capability(
        agent_id: str,
        skill: str,
    ) -> AgentResponse:
        """
        Remove a capability from an agent.

        **Parameters:**
        - agent_id: Agent ID
        - skill: Skill name to remove

        **Returns:**
        - 200 OK: Capability removed successfully
        - 400 Bad Request: Capability not found or it's the last capability
        - 401 Unauthorized: Authentication required
        - 404 Not Found: Agent not found

        **Note:** Cannot remove the last capability from an agent.
        """
        try:
            command = RemoveAgentCapabilityCommand(
                agent_id=agent_id,
                skill=skill,
            )

            # Execute command via port
            agent = await command_port.remove_capability(command)

            # Retrieve updated agent
            agent_info = await query_port.get_agent(agent.id, include_stats=True)

            return AgentMapper.to_response(agent_info)

        except Exception as e:
            if "not found" in str(e).lower():
                if "agent" in str(e).lower():
                    raise HTTPException(
                        status_code=status.HTTP_404_NOT_FOUND,
                        detail=f"Agent not found: {str(e)}",
                    )
                else:
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail=f"Capability not found: {str(e)}",
                    )
            elif "last capability" in str(e).lower():
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Cannot remove last capability from agent",
                )
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Failed to remove capability: {str(e)}",
            )

    @router.patch(
        "/{agent_id}/capabilities/{skill}",
        response_model=AgentResponse,
        summary="Update capability proficiency",
        response_description="Updated agent with modified capability",
    )
    async def update_capability(
        agent_id: str,
        skill: str,
        request: UpdateCapabilityRequest,
    ) -> AgentResponse:
        """
        Update the proficiency level of an agent's capability.

        **Parameters:**
        - agent_id: Agent ID
        - skill: Skill name to update

        **Request Body:**
        - proficiency: New proficiency level (0.0 to 1.0)

        **Returns:**
        - 200 OK: Proficiency updated successfully
        - 400 Bad Request: Capability not found or invalid proficiency
        - 401 Unauthorized: Authentication required
        - 404 Not Found: Agent not found
        """
        try:
            command = UpdateAgentCapabilityCommand(
                agent_id=agent_id,
                skill=skill,
                proficiency=request.proficiency,
            )

            # Execute command via port
            agent = await command_port.update_capability(command)

            # Retrieve updated agent
            agent_info = await query_port.get_agent(agent.id, include_stats=True)

            return AgentMapper.to_response(agent_info)

        except Exception as e:
            if "not found" in str(e).lower():
                if "agent" in str(e).lower():
                    raise HTTPException(
                        status_code=status.HTTP_404_NOT_FOUND,
                        detail=f"Agent not found: {str(e)}",
                    )
                else:
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail=f"Capability not found: {str(e)}",
                    )
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Failed to update capability: {str(e)}",
            )

    # ========================================================================
    # MCP Server Management
    # ========================================================================

    @router.post(
        "/{agent_id}/mcp-servers",
        response_model=AgentResponse,
        summary="Add MCP server to agent",
        response_description="Updated agent with new MCP server",
    )
    async def add_mcp_server(
        agent_id: str,
        request: AddMcpServerRequest,
    ) -> AgentResponse:
        """
        Add an MCP server to agent configuration.

        **Parameters:**
        - agent_id: Agent ID

        **Request Body:**
        - server_name: MCP server name

        **Returns:**
        - 200 OK: MCP server added successfully
        - 400 Bad Request: Server already configured
        - 401 Unauthorized: Authentication required
        - 404 Not Found: Agent not found
        """
        try:
            command = AddMcpServerCommand(
                agent_id=agent_id,
                server_name=request.server_name,
            )

            # Execute command via port
            agent = await command_port.add_mcp_server(command)

            # Retrieve updated agent
            agent_info = await query_port.get_agent(agent.id, include_stats=True)

            return AgentMapper.to_response(agent_info)

        except Exception as e:
            if "not found" in str(e).lower():
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"Agent not found: {str(e)}",
                )
            elif "already" in str(e).lower():
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"MCP server already configured: {str(e)}",
                )
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Failed to add MCP server: {str(e)}",
            )

    @router.delete(
        "/{agent_id}/mcp-servers/{server_name}",
        response_model=AgentResponse,
        summary="Remove MCP server from agent",
        response_description="Updated agent without removed MCP server",
    )
    async def remove_mcp_server(
        agent_id: str,
        server_name: str,
    ) -> AgentResponse:
        """
        Remove an MCP server from agent configuration.

        **Parameters:**
        - agent_id: Agent ID
        - server_name: MCP server name to remove

        **Returns:**
        - 200 OK: MCP server removed successfully
        - 400 Bad Request: Server not configured
        - 401 Unauthorized: Authentication required
        - 404 Not Found: Agent not found
        """
        try:
            command = RemoveMcpServerCommand(
                agent_id=agent_id,
                server_name=server_name,
            )

            # Execute command via port
            agent = await command_port.remove_mcp_server(command)

            # Retrieve updated agent
            agent_info = await query_port.get_agent(agent.id, include_stats=True)

            return AgentMapper.to_response(agent_info)

        except Exception as e:
            if "not found" in str(e).lower():
                if "agent" in str(e).lower():
                    raise HTTPException(
                        status_code=status.HTTP_404_NOT_FOUND,
                        detail=f"Agent not found: {str(e)}",
                    )
                else:
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail=f"MCP server not configured: {str(e)}",
                    )
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Failed to remove MCP server: {str(e)}",
            )

    # ========================================================================
    # Delete Agent
    # ========================================================================

    @router.delete(
        "/{agent_id}",
        response_model=AgentCommandResult,
        summary="Delete agent (soft delete)",
        response_description="Deletion result",
    )
    async def delete_agent(agent_id: str) -> AgentCommandResult:
        """
        Delete an agent (soft delete).

        **Parameters:**
        - agent_id: Agent ID

        **Returns:**
        - 200 OK: Agent deleted successfully
        - 401 Unauthorized: Authentication required
        - 404 Not Found: Agent not found

        **Note:**
        - This is a soft delete - agent is marked as deleted but preserved in event store
        - Agent will not appear in list queries after deletion
        - Event history is preserved for audit trail
        """
        try:
            # Execute command via port
            result = await command_port.delete_agent(agent_id)

            # Convert to response DTO
            return AgentMapper.to_command_result(result)

        except Exception as e:
            if "not found" in str(e).lower():
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"Agent not found: {str(e)}",
                )
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Failed to delete agent: {str(e)}",
            )

    return router


# ============================================================================
# Helper Functions
# ============================================================================
# (No helper functions needed - masking is handled in the mapper)
