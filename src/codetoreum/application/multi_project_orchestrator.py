"""Multi-project orchestrator application service.

Provides admin query methods for project status and enabled projects list.
Lifecycle initialization is handled by ProjectLifecycleService.
"""

import logging

from codetoreum.ports.exceptions import (
    ResourceNotFoundError,
)
from codetoreum.ports.output.multi_project_orchestrator import (
    IMultiProjectOrchestrator,
    ProjectStatus,
)
from codetoreum.ports.output.project_manager_service import IProjectManagerService

logger = logging.getLogger(__name__)


class MultiProjectOrchestrator(IMultiProjectOrchestrator):
    """Provides admin query methods for project status and monitoring.

    Note: Project lifecycle initialization is handled by ProjectLifecycleService.
    The application is fully event-driven; orchestration is triggered by
    WorkItemColumnChangedEvent and other domain events emitted by adapters.
    Adapter-level polling (e.g., in GitHubBoardAdapter) is the adapter's
    private concern and does not cross the hexagonal boundary.
    """

    def __init__(
        self,
        project_manager: IProjectManagerService,
    ) -> None:
        """Initialize the multi-project orchestrator.

        Args:
            project_manager: Service for managing project configurations
        """
        self._project_manager = project_manager


    async def get_project_status(self, project_name: str) -> ProjectStatus:
        """Get current orchestration status for a project.

        Returns:
            ProjectStatus with project configuration and status information.

        Raises:
            ResourceNotFoundError: Project doesn't exist
        """
        config = await self._project_manager.get_project_config(project_name)
        workspace_path = await self._project_manager.get_project_path(project_name)

        return ProjectStatus(
            project_name=project_name,
            enabled=config.enabled,
            repo_url=config.repo_url,
            branch=config.branch,
            organization=config.org,
            workspace_path=workspace_path,
        )

    async def list_enabled_projects(self) -> list[str]:
        """Get list of all enabled projects.

        Returns:
            List of enabled project names

        Raises:
            ExternalServiceError: Configuration service failure
        """
        return await self._project_manager.get_enabled_projects()

