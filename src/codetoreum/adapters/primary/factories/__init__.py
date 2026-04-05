"""
Factory functions for creating FastAPI application instances.
"""

from codetoreum.adapters.primary.factories.lifespan import create_lifespan
from codetoreum.adapters.primary.factories.production import (
    create_branch_resolution_adapter,
    create_workspace_router_with_branch_resolution,
)
from codetoreum.adapters.primary.fastapi_app import create_app, create_development_app

__all__ = [
    "create_app",
    "create_development_app",
    "create_lifespan",
    "create_branch_resolution_adapter",
    "create_workspace_router_with_branch_resolution",
]
