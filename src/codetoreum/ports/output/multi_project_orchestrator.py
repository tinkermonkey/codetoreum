"""Multi-project orchestrator port interface.

This interface defines contracts for orchestrating work across multiple
independent projects within a single orchestrator process. The orchestrator
coordinates project initialization, per-project workflow execution, and
cross-project state management.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class ProjectStatus:
    """Status information for a single project.

    Attributes: project_name: Name of the project
        enabled: Whether the project is enabled for orchestration
        repo_url: Repository URL for the project
        branch: Default branch for the project
        organization: Organization/owner of the project
        workspace_path: Filesystem path where project workspace is mounted
    """

    project_name: str
    enabled: bool
    repo_url: str
    branch: str
    organization: str
    workspace_path: str


@dataclass(frozen=True)
class OrchestrationCycleResult:
    """Result of a single orchestration cycle.

    Attributes: success: Whether the cycle completed without critical errors
        projects_processed: Number of projects processed
        total_actions: Total actions taken across all projects
        total_errors: Total errors encountered
        cycle_duration_ms: Duration of the cycle in milliseconds (as integer)
        timestamp: When the cycle completed
        error_message: Error message if cycle failed
    """

    success: bool
    projects_processed: int
    total_actions: int
    total_errors: int
    cycle_duration_ms: int
    timestamp: datetime
    error_message: str | None = None


@dataclass(frozen=True)
class ProjectOrchestrationResult:
    """Result of orchestrating a single project.

    Attributes: project_name: Name of the project
        success: Whether project orchestration succeeded
        actions_taken: Number of actions taken for this project
        errors: Tuple of errors encountered (immutable)
        workspace_path: Path to the project's workspace
        timestamp: When orchestration completed
    """

    project_name: str
    success: bool
    actions_taken: int
    errors: tuple[str, ...]
    workspace_path: str
    timestamp: datetime


class IMultiProjectOrchestrator(ABC):
    """Output port for project administration and status queries.

    Provides admin query methods for project status and enabled projects list.

    Note: In Phase 7, application-layer polling was removed. Project lifecycle
    initialization is now handled by ProjectLifecycleService. The application
    is fully event-driven; orchestration is triggered by WorkItemColumnChangedEvent
    and other domain events emitted by adapters.
    """

    @abstractmethod
    async def get_project_status(self, project_name: str) -> ProjectStatus:
        """Get current orchestration status for a project.

        Returns basic project information:
        - Project name
        - Enabled status
        - Repository URL and branch
        - Organization/owner
        - Workspace filesystem path

        Args: project_name: Name of the project

        Returns: ProjectStatus with project configuration and path information

        Raises: ResourceNotFoundError: Project doesn't exist
        """

    @abstractmethod
    async def list_enabled_projects(self) -> list[str]:
        """Get list of all enabled projects.

        Returns project names that are configured and enabled.

        Returns: List of enabled project names

        Raises: ExternalServiceError: Configuration service failure
        """
