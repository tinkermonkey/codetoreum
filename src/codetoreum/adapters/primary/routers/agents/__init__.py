"""
Agents REST API Router

Provides RESTful endpoints for agent registry operations including
listing, configuring, and managing agents with capabilities and execution stats.

This module is organized into sub-modules:
- list.py: List and filter agents
- crud.py: Create, update, delete agents
- capabilities.py: Manage agent capabilities
- mcp_servers.py: Manage MCP server configurations
"""

from typing import Optional

from fastapi import APIRouter, Depends

from codetoreum.adapters.primary.simple_auth_dependencies import SimpleAuthDependencies
from codetoreum.ports.input.agent_command import IAgentCommandPort
from codetoreum.ports.input.agent_query import IAgentQueryPort

# Import sub-module registration functions
from codetoreum.adapters.primary.routers.agents.list import register_list_endpoints
from codetoreum.adapters.primary.routers.agents.crud import register_crud_endpoints
from codetoreum.adapters.primary.routers.agents.capabilities import (
    register_capability_endpoints,
)
from codetoreum.adapters.primary.routers.agents.mcp_servers import (
    register_mcp_server_endpoints,
)


def create_agents_router(
    command_port: IAgentCommandPort,
    query_port: IAgentQueryPort,
    auth_deps: Optional[SimpleAuthDependencies] = None,
) -> APIRouter:
    """
    Create the agents REST API router.

    This function creates a FastAPI router and registers all agent-related
    endpoints organized by functionality:
    - List/search endpoints
    - CRUD operations
    - Capability management
    - MCP server management

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

    # Register endpoints from sub-modules
    register_list_endpoints(router, query_port)
    register_crud_endpoints(router, command_port, query_port)
    register_capability_endpoints(router, command_port, query_port)
    register_mcp_server_endpoints(router, command_port, query_port)

    return router


__all__ = ["create_agents_router"]
