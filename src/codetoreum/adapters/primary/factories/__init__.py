"""
Factory functions for creating FastAPI application instances.

This module consolidates application and service creation factories:
- Core app factories: create_app, create_development_app (from fastapi_app module)
- Lifespan management: create_lifespan (for application startup/shutdown)
- Production bootstrap: create_branch_resolution_adapter, create_workspace_router_with_branch_resolution
  (for wiring intelligent branch resolution into production environments)

**Import Note**: In PR #661, the core app factories were consolidated from separate app_factory and
development modules into a single fastapi_app module. This change is reflected here as of that PR.
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
