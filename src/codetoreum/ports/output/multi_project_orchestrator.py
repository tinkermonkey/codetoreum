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

    Attributes:
        project_name: Name of the project
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

    Attributes:
        success: Whether the cycle completed without critical errors
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

    Attributes:
        project_name: Name of the project
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
    """Output port for orchestrating multiple projects.

    Coordinates workflow execution across multiple independent projects,
    handling project initialization, per-project orchestration, and
    cross-project state management.

    Responsibilities:
    1. Load and track enabled projects
    2. Ensure project repositories are cloned and available
    3. Execute per-project orchestration cycles
    4. Handle project-specific state isolation (per-project locking, queueing)
    5. Emit orchestration events for observability and audit trail

    Project Orchestration:
    - Each project has its own workflow, pipeline, and board configuration
    - Projects execute independently but share orchestration infrastructure
    - State (locks, queues, sessions) is isolated per project via namespacing
    - Repository workspaces are isolated per project repository

    Orchestration Cycles:
    - Full cycle: reload config → get enabled projects → process each project
    - Per-project: ensure cloned → orchestrate workflows → emit events
    - Errors in one project don't block others

    Example:
        async with orchestrator as orch:
            # Run a complete orchestration cycle
            result = await orch.run_orchestration_cycle()
            assert result.success
            assert result.projects_processed > 0
    """

    @abstractmethod
    async def run_orchestration_cycle(self) -> OrchestrationCycleResult:
        """Execute a complete orchestration cycle across all enabled projects.

        Operations:
        1. Reload project configurations (detect added/removed projects)
        2. Get list of enabled projects
        3. For each enabled project:
           a. Ensure project repository is cloned
           b. Execute per-project workflow orchestration
           c. Collect results and errors
        4. Emit orchestration events
        5. Return aggregated cycle result

        Error Handling:
        - Errors in one project don't block others
        - Clone failures emit ProjectCloneFailedEvent, processing continues
        - Workflow errors logged per project, not blocking overall cycle

        Returns:
            OrchestrationCycleResult: Aggregated results across all projects

        Raises:
            ExternalServiceError: Critical infrastructure failure
        """

    @abstractmethod
    async def orchestrate_project(self, project_name: str) -> ProjectOrchestrationResult:
        """Execute orchestration for a single project.

        Operations:
        1. Load project configuration
        2. Ensure repository is cloned
        3. Execute workflow orchestration for the project
        4. Collect and return results

        Args:
            project_name: Name of the project to orchestrate

        Returns:
            ProjectOrchestrationResult: Results for this project

        Raises:
            ResourceNotFoundError: Project configuration doesn't exist
            ExternalServiceError: Repository clone/orchestration failed
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

        Args:
            project_name: Name of the project

        Returns:
            ProjectStatus with project configuration and path information

        Raises:
            ResourceNotFoundError: Project doesn't exist
        """

    @abstractmethod
    async def list_enabled_projects(self) -> list[str]:
        """Get list of all enabled projects.

        Returns project names that are configured and enabled.

        Returns:
            List of enabled project names

        Raises:
            ExternalServiceError: Configuration service failure
        """
