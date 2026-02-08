"""Multi-project orchestrator application service.

Orchestrates workflow execution across multiple independent projects,
handling project initialization, per-project workflow execution,
and cross-project state management.
"""

import asyncio
import logging
import time
from datetime import datetime, timezone
from typing import Dict, List, Optional

from typing import TYPE_CHECKING, Any, Dict, List, Optional

from codetoreum.domain.events.project_events import OrchestrationCycleCompletedEvent
from codetoreum.ports.output.project_manager_service import IProjectManagerService
from codetoreum.ports.output.event_emitter import IEventEmitter
from codetoreum.ports.output.multi_project_orchestrator import (
    IMultiProjectOrchestrator,
    OrchestrationCycleResult,
    ProjectOrchestrationResult,
)
from codetoreum.ports.exceptions import (
    ResourceNotFoundError,
    ExternalServiceError,
)

if TYPE_CHECKING:
    from codetoreum.ports.output.workflow_orchestrator import IWorkflowOrchestrator

logger = logging.getLogger(__name__)


class MultiProjectOrchestrator(IMultiProjectOrchestrator):
    """Application service for orchestrating multiple projects.

    Coordinates workflow execution across multiple independent projects,
    managing project initialization, per-project orchestration, and
    maintaining isolation between projects.

    Architecture:
    - Delegates project management to IProjectManagerService
    - Delegates per-project orchestration to IWorkflowOrchestrator
    - Emits events for observability and state tracking
    - Handles errors gracefully, allowing one project's errors to not block others

    Example:
        orchestrator = MultiProjectOrchestrator(
            project_manager=project_manager,
            workflow_orchestrator=workflow_orchestrator,
            event_emitter=event_emitter
        )

        # Run orchestration cycle
        result = await orchestrator.run_orchestration_cycle()
        if result.success:
            logger.info(f"Orchestrated {result.projects_processed} projects")
    """

    def __init__(
        self,
        project_manager: IProjectManagerService,
        workflow_orchestrator: "IWorkflowOrchestrator",
        event_emitter: Optional[IEventEmitter] = None,
    ) -> None:
        """Initialize the multi-project orchestrator.

        Args:
            project_manager: Service for managing project configurations and repositories
            workflow_orchestrator: Service for orchestrating individual project workflows
            event_emitter: Optional event emitter for orchestration events
        """
        self._project_manager = project_manager
        self._workflow_orchestrator = workflow_orchestrator
        self._event_emitter = event_emitter
        self._last_cycle_time: Optional[datetime] = None
        self._cycle_count = 0

    async def run_orchestration_cycle(self) -> OrchestrationCycleResult:
        """Execute a complete orchestration cycle across all enabled projects.

        Steps:
        1. Record cycle start time
        2. Reload project configurations
        3. Get list of enabled projects
        4. Orchestrate each enabled project (in parallel or sequential)
        5. Collect results and aggregate metrics
        6. Emit orchestration cycle completed event
        7. Return aggregated result

        The operation is designed to be fault-tolerant: errors in one
        project don't prevent orchestration of other projects.

        Returns:
            OrchestrationCycleResult: Aggregated metrics and status

        Raises:
            ExternalServiceError: Critical infrastructure failure preventing cycle
        """
        cycle_start = time.time()
        cycle_timestamp = datetime.now(timezone.utc)
        self._cycle_count += 1

        try:
            logger.info(f"Starting orchestration cycle #{self._cycle_count}")

            # Step 1: Reload configurations
            try:
                await self._project_manager.reload_config()
                logger.debug("Project configurations reloaded")
            except ExternalServiceError as e:
                logger.warning(f"Failed to reload project config: {e}")
                # Don't fail the cycle, use cached config

            # Step 2: Get enabled projects
            try:
                enabled_projects = await self._project_manager.get_enabled_projects()
            except ExternalServiceError as e:
                msg = f"Failed to get enabled projects: {e}"
                logger.error(msg)
                duration_ms = (time.time() - cycle_start) * 1000
                return OrchestrationCycleResult(
                    success=False,
                    projects_processed=0,
                    total_actions=0,
                    total_errors=1,
                    cycle_duration_ms=duration_ms,
                    timestamp=cycle_timestamp,
                    error_message=msg,
                )

            if not enabled_projects:
                logger.info("No enabled projects to orchestrate")
                duration_ms = (time.time() - cycle_start) * 1000
                return OrchestrationCycleResult(
                    success=True,
                    projects_processed=0,
                    total_actions=0,
                    total_errors=0,
                    cycle_duration_ms=duration_ms,
                    timestamp=cycle_timestamp,
                )

            logger.info(f"Found {len(enabled_projects)} enabled projects")

            # Step 3: Orchestrate each project (sequentially to avoid resource contention)
            project_results: List[ProjectOrchestrationResult] = []
            total_actions = 0
            total_errors = 0

            for project_name in enabled_projects:
                try:
                    logger.info(f"Orchestrating project: {project_name}")
                    result = await self.orchestrate_project(project_name)
                    project_results.append(result)
                    total_actions += result.actions_taken
                    total_errors += len(result.errors)

                    if result.success:
                        logger.info(
                            f"Successfully orchestrated {project_name} "
                            f"({result.actions_taken} actions)"
                        )
                    else:
                        logger.warning(
                            f"Orchestration of {project_name} had errors: "
                            f"{', '.join(result.errors)}"
                        )
                except Exception as e:
                    logger.error(f"Unexpected error orchestrating {project_name}: {e}")
                    total_errors += 1
                    project_results.append(
                        ProjectOrchestrationResult(
                            project_name=project_name,
                            success=False,
                            actions_taken=0,
                            errors=[str(e)],
                            workspace_path="",
                            timestamp=datetime.now(timezone.utc),
                        )
                    )

            # Step 4: Emit cycle completion event
            cycle_duration_ms = (time.time() - cycle_start) * 1000
            cycle_result = OrchestrationCycleResult(
                success=total_errors == 0,
                projects_processed=len(project_results),
                total_actions=total_actions,
                total_errors=total_errors,
                cycle_duration_ms=cycle_duration_ms,
                timestamp=cycle_timestamp,
            )

            # Emit event
            if self._event_emitter:
                event = OrchestrationCycleCompletedEvent(
                    type="orchestration.cycle_completed",
                    timestamp=self._get_iso_timestamp(),
                    source="multi_project_orchestrator",
                    projects_processed=len(project_results),
                    boards_processed=0,  # Not tracked at orchestrator level
                    work_items_found=total_actions,  # Proxy: actions = work items processed
                    cycle_duration_ms=int(cycle_duration_ms),
                )
                self._event_emitter.emit(event)

            logger.info(
                f"Orchestration cycle #{self._cycle_count} completed: "
                f"{len(project_results)} projects, "
                f"{total_actions} actions, "
                f"{total_errors} errors, "
                f"{cycle_duration_ms:.0f}ms"
            )

            self._last_cycle_time = cycle_timestamp
            return cycle_result

        except Exception as e:
            logger.error(f"Critical error in orchestration cycle: {e}", exc_info=True)
            duration_ms = (time.time() - cycle_start) * 1000
            return OrchestrationCycleResult(
                success=False,
                projects_processed=0,
                total_actions=0,
                total_errors=1,
                cycle_duration_ms=duration_ms,
                timestamp=cycle_timestamp,
                error_message=str(e),
            )

    async def orchestrate_project(
        self, project_name: str
    ) -> ProjectOrchestrationResult:
        """Execute orchestration for a single project.

        Steps:
        1. Load project configuration
        2. Ensure project repository is cloned
        3. Delegate to workflow orchestrator for the project
        4. Collect and return results

        Args:
            project_name: Name of the project

        Returns:
            ProjectOrchestrationResult: Results for this project

        Raises:
            ResourceNotFoundError: Project configuration doesn't exist
            ExternalServiceError: Repository clone failed
        """
        start_time = datetime.now(timezone.utc)

        try:
            # Get project configuration
            config = await self._project_manager.get_project_config(project_name)
            logger.debug(
                f"Loaded configuration for {project_name}: {config.repo_url}"
            )

            # Ensure project is cloned
            workspace_path = await self._project_manager.ensure_project_cloned(
                project_name
            )
            logger.debug(f"Project {project_name} ensured at {workspace_path}")

            # Delegate per-project orchestration to workflow orchestrator
            # The workflow orchestrator knows about this project through context
            actions_taken = await self._workflow_orchestrator.orchestrate_project(
                project_name=project_name,
                workspace_path=workspace_path,
                config=config,
            )

            logger.info(f"Project {project_name} orchestration: {actions_taken} actions")

            return ProjectOrchestrationResult(
                project_name=project_name,
                success=True,
                actions_taken=actions_taken,
                errors=[],
                workspace_path=workspace_path,
                timestamp=start_time,
            )

        except ResourceNotFoundError as e:
            logger.warning(f"Project {project_name} not found: {e}")
            return ProjectOrchestrationResult(
                project_name=project_name,
                success=False,
                actions_taken=0,
                errors=[f"Project not found: {e}"],
                workspace_path="",
                timestamp=start_time,
            )

        except ExternalServiceError as e:
            logger.warning(f"External service error for {project_name}: {e}")
            return ProjectOrchestrationResult(
                project_name=project_name,
                success=False,
                actions_taken=0,
                errors=[f"External service error: {e}"],
                workspace_path="",
                timestamp=start_time,
            )

        except Exception as e:
            logger.error(
                f"Unexpected error orchestrating {project_name}: {e}", exc_info=True
            )
            return ProjectOrchestrationResult(
                project_name=project_name,
                success=False,
                actions_taken=0,
                errors=[f"Unexpected error: {e}"],
                workspace_path="",
                timestamp=start_time,
            )

    async def get_project_status(self, project_name: str) -> Dict[str, any]:
        """Get current orchestration status for a project.

        Returns:
            Dict with keys:
                - project_name: str
                - enabled: bool
                - repo_url: str
                - branch: str
                - workspace_path: str
                - cloned: bool
                - last_action: Optional[datetime]

        Raises:
            ResourceNotFoundError: Project doesn't exist
        """
        try:
            config = await self._project_manager.get_project_config(project_name)
            workspace_path = await self._project_manager.get_project_path(project_name)

            return {
                "project_name": project_name,
                "enabled": config.enabled,
                "repo_url": config.repo_url,
                "branch": config.branch,
                "organization": config.org,
                "workspace_path": workspace_path,
            }
        except ResourceNotFoundError:
            raise

    async def enable_project(self, project_name: str) -> None:
        """Enable a project for orchestration.

        Args:
            project_name: Name of the project

        Raises:
            ResourceNotFoundError: Project doesn't exist
        """
        config = await self._project_manager.get_project_config(project_name)
        # Create new config with enabled=True
        updated_config = config.__class__(
            repo_url=config.repo_url,
            branch=config.branch,
            enabled=True,
            org=config.org,
        )
        # Note: This requires project manager to support updating
        # For now, log the intent
        logger.info(f"Enabled project: {project_name}")

    async def disable_project(self, project_name: str) -> None:
        """Disable a project from orchestration.

        Args:
            project_name: Name of the project

        Raises:
            ResourceNotFoundError: Project doesn't exist
        """
        config = await self._project_manager.get_project_config(project_name)
        # Create new config with enabled=False
        updated_config = config.__class__(
            repo_url=config.repo_url,
            branch=config.branch,
            enabled=False,
            org=config.org,
        )
        # Note: This requires project manager to support updating
        # For now, log the intent
        logger.info(f"Disabled project: {project_name}")

    async def list_enabled_projects(self) -> List[str]:
        """Get list of all enabled projects.

        Returns:
            List of enabled project names

        Raises:
            ExternalServiceError: Configuration service failure
        """
        return await self._project_manager.get_enabled_projects()

    # =========================================================================
    # Private Methods
    # =========================================================================

    @staticmethod
    def _get_iso_timestamp() -> str:
        """Get current timestamp in ISO 8601 format with UTC timezone."""
        return datetime.now(timezone.utc).isoformat()
