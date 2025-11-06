"""
Agent MCP Server Endpoints

Provides endpoints for managing MCP server configurations on agents.
"""

from fastapi import APIRouter, HTTPException, status

from codetoreum.adapters.primary.agent_dtos import (
    AddMcpServerRequest,
    AgentResponse,
)
from codetoreum.adapters.primary.agent_mappers import AgentMapper
from codetoreum.ports.input.agent_command import (
    IAgentCommandPort,
    AddMcpServerCommand,
    RemoveMcpServerCommand,
)
from codetoreum.ports.input.agent_query import IAgentQueryPort


def register_mcp_server_endpoints(
    router: APIRouter,
    command_port: IAgentCommandPort,
    query_port: IAgentQueryPort,
) -> None:
    """
    Register MCP server management endpoints on the given router.

    Args:
        router: APIRouter to register endpoints on
        command_port: Agent command port for mutations
        query_port: Agent query port for data access
    """

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

        except (ValueError, KeyError, AttributeError) as e:
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

        except (ValueError, KeyError, AttributeError) as e:
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
