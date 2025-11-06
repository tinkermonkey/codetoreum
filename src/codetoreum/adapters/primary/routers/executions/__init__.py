"""
Executions REST API Router

Modular structure for execution monitoring endpoints:
- list: Execution list with filtering and pagination
- detail: Detailed execution status and event history
- logs: Container logs retrieval
- control: Execution lifecycle control (terminate, etc.)
"""

from typing import Optional

from fastapi import APIRouter, Depends

from codetoreum.adapters.primary.simple_auth_dependencies import SimpleAuthDependencies
from codetoreum.ports.input.execution_command import IExecutionCommandPort
from codetoreum.ports.input.execution_query import IExecutionQueryPort

from .control import register_control_endpoints
from .detail import register_detail_endpoints
from .list import register_list_endpoints
from .logs import register_logs_endpoints


def create_executions_router(
    command_port: IExecutionCommandPort,
    query_port: IExecutionQueryPort,
    auth_deps: Optional[SimpleAuthDependencies] = None,
) -> APIRouter:
    """
    Create the executions REST API router.

    Args:
        command_port: Execution command input port
        query_port: Execution query input port
        auth_deps: Optional authentication dependencies

    Returns:
        Configured APIRouter for executions
    """
    # Create router with authentication dependency if provided
    router_kwargs = {
        "prefix": "/api/v2/executions",
        "tags": ["executions"],
    }
    if auth_deps:
        router_kwargs["dependencies"] = [Depends(auth_deps.require_auth)]

    router = APIRouter(**router_kwargs)

    # Register all endpoint groups
    register_list_endpoints(router, query_port)
    register_detail_endpoints(router, query_port)
    register_logs_endpoints(router, query_port)
    register_control_endpoints(router, command_port)

    return router


# Re-export for backward compatibility
__all__ = ["create_executions_router"]
