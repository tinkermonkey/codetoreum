"""
Configuration REST API Router

Modular structure for configuration management endpoints:
- projects: Project configuration CRUD
- agents: Agent configuration CRUD
- pipelines: Pipeline configuration CRUD
- environment: Environment variable management
- search: Full-text configuration search
"""

from typing import Optional

from fastapi import APIRouter, Depends

from codetoreum.adapters.primary.simple_auth_dependencies import SimpleAuthDependencies
from codetoreum.ports.input.config_command import IConfigurationCommandPort
from codetoreum.ports.input.config_query import IConfigurationQueryPort

from .agents import register_agent_endpoints
from .environment import register_environment_endpoints
from .import_export import register_import_export_endpoints
from .pipelines import register_pipeline_endpoints
from .projects import register_project_endpoints
from .search import register_search_endpoints


def create_config_router(
    command_port: IConfigurationCommandPort,
    query_port: IConfigurationQueryPort,
    auth_deps: SimpleAuthDependencies | None = None,
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

    # Register all endpoint groups
    register_project_endpoints(router, command_port, query_port)
    register_agent_endpoints(router, command_port, query_port)
    register_pipeline_endpoints(router, command_port, query_port)
    register_environment_endpoints(router, command_port, query_port)
    register_search_endpoints(router, query_port)
    register_import_export_endpoints(router)

    return router


# Re-export for backward compatibility
__all__ = ["create_config_router"]
