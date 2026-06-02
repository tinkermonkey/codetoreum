"""Project administration REST API router.

Provides endpoints for project management operations such as querying
project status and listing enabled projects.
"""

from fastapi import APIRouter, Depends, HTTPException, status

from codetoreum.adapters.primary.simple_auth_dependencies import SimpleAuthDependencies
from codetoreum.ports.exceptions import ResourceNotFoundError
from codetoreum.ports.output.multi_project_orchestrator import (
    IMultiProjectOrchestrator,
    ProjectStatus,
)


def create_projects_router(
    multi_project_orchestrator: IMultiProjectOrchestrator,
    auth_deps: SimpleAuthDependencies | None = None,
) -> APIRouter:
    """Create the projects administration REST API router.

    Args:
        multi_project_orchestrator: Multi-project orchestrator for status queries
        auth_deps: Optional authentication dependencies

    Returns:
        Configured APIRouter for projects administration
    """
    router_kwargs = {
        "prefix": "/api/v2/admin/projects",
        "tags": ["admin", "projects"],
    }
    if auth_deps:
        router_kwargs["dependencies"] = [Depends(auth_deps.require_auth)]

    router = APIRouter(**router_kwargs)

    @router.get(
        "/",
        response_model=list[str],
        summary="List enabled projects",
        response_description="List of enabled project names",
    )
    async def list_enabled_projects() -> list[str]:
        """
        Get list of all enabled projects.

        Returns:
            - 200 OK: List of enabled project names
            - 401 Unauthorized: Authentication required
            - 500 Internal Server Error: Service failure
        """
        try:
            projects = await multi_project_orchestrator.list_enabled_projects()
            return projects
        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to list projects: {e!s}",
            )

    @router.get(
        "/{project_name}",
        response_model=ProjectStatus,
        summary="Get project status",
        response_description="Project configuration and status information",
    )
    async def get_project_status(project_name: str) -> ProjectStatus:
        """
        Get current status for a specific project.

        **Parameters:**
        - project_name: Name of the project

        Returns:
            - 200 OK: Project status information
            - 401 Unauthorized: Authentication required
            - 404 Not Found: Project doesn't exist
            - 500 Internal Server Error: Service failure

        **Response includes:**
        - project_name: Name of the project
        - enabled: Whether the project is enabled
        - repo_url: Repository URL
        - branch: Configured branch
        - organization: Organization name
        - workspace_path: Local workspace path
        """
        try:
            status_info = await multi_project_orchestrator.get_project_status(project_name)
            return status_info
        except ResourceNotFoundError:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Project '{project_name}' not found",
            )
        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to get project status: {e!s}",
            )

    return router
