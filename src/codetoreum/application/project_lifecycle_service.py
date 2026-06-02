"""Project lifecycle service for managing project initialization and setup.

Handles project-level lifecycle operations that were previously in the
MultiProjectOrchestrator polling loop, now executed once at bootstrap time
or triggered via admin endpoints.
"""

import logging

from codetoreum.ports.exceptions import (
    ExternalServiceError,
    ResourceNotFoundError,
)
from codetoreum.ports.output.board_service import BoardConfig, IBoardService
from codetoreum.ports.output.project_manager_service import IProjectManagerService

logger = logging.getLogger(__name__)


class ProjectLifecycleService:
    """Service for project lifecycle operations.

    Handles:
    - Initial board reconciliation for enabled projects
    - Project registration and setup
    """

    def __init__(
        self,
        project_manager: IProjectManagerService,
        board_service: IBoardService | None = None,
    ) -> None:
        """Initialize project lifecycle service.

        Args:
            project_manager: Service for managing project configurations
            board_service: Optional board service for reconciliation
        """
        self._project_manager = project_manager
        self._board_service = board_service

    async def initialize_all_projects(self) -> None:
        """Initialize all enabled projects on bootstrap.

        Reconciles all project boards for enabled projects.
        Continues on errors (non-blocking failures).
        """
        try:
            enabled_projects = await self._project_manager.get_enabled_projects()

            logger.info(
                f"Initializing {len(enabled_projects)} projects",
                extra={"project_count": len(enabled_projects)},
            )

            for project_name in enabled_projects:
                try:
                    await self._reconcile_project_boards(project_name)
                except (ExternalServiceError, ResourceNotFoundError) as e:
                    logger.warning(
                        f"Board reconciliation failed for {project_name}: {e}",
                        exc_info=True,
                        extra={
                            "error_id": "ERR_PROJECT_LIFECYCLE_RECONCILIATION_FAILED",
                            "project_name": project_name,
                        },
                    )
                    # Continue with other projects

        except (ExternalServiceError, ResourceNotFoundError) as e:
            logger.warning(
                f"Project initialization failed: {e}",
                exc_info=True,
                extra={"error_id": "ERR_PROJECT_LIFECYCLE_INITIALIZATION_FAILED"},
            )
            # Don't propagate - allow bootstrap to continue

    async def _reconcile_project_boards(self, project_name: str) -> None:
        """Reconcile boards for a specific project.

        Args:
            project_name: Name of the project

        Raises:
            ExternalServiceError: Board reconciliation failed
        """
        if self._board_service is None:
            logger.debug(
                f"Skipping board reconciliation for {project_name} (board service not configured)",
                extra={"project_name": project_name},
            )
            return

        try:
            project_config = await self._project_manager.get_project_config(project_name)
            metadata = getattr(project_config, "metadata", {})
            github_project_id = metadata.get("github_project_id") if hasattr(metadata, "get") else None
        except Exception:
            github_project_id = None

        if not github_project_id:
            logger.debug(
                f"Skipping board reconciliation for {project_name}: no github_project_id in project metadata",
                extra={"project_name": project_name},
            )
            return

        logger.debug(
            f"Reconciling boards for project {project_name} (node_id={github_project_id})",
            extra={"project_name": project_name},
        )
        await self._board_service.reconcile_board(
            github_project_id, BoardConfig(board_id=project_name, expected_columns=())
        )
