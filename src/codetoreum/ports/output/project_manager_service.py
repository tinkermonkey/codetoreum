"""Project management service port interface for multi-project orchestration.

This interface defines contracts for managing multiple project configurations,
ensuring repositories are cloned and updated, and coordinating work across
multiple independent projects within a single orchestrator process.

Projects are loaded from configuration (e.g., projects.yaml) and processed
selectively based on enabled status. Each project maintains isolated state
while sharing orchestration infrastructure.
"""

from abc import ABC, abstractmethod
from typing import List

from codetoreum.domain.value_objects import ProjectConfig


class IProjectManagerService(ABC):
    """Output port for managing multiple project configurations.

    Provides access to project configurations and ensures repositories
    are cloned and updated for agent execution. Acts as a facade over
    project configuration storage and repository management operations.

    Responsibilities:
    1. Load and maintain project configurations
    2. Filter enabled projects for processing
    3. Ensure repositories are cloned and up-to-date
    4. Derive workspace paths from repository URLs
    5. Support configuration reloading on orchestration cycles

    Project Configuration:
    - Loaded from a configuration source (e.g., projects.yaml file)
    - Defines: repo URL, branch, enabled status, organization namespace
    - Can be changed between orchestration cycles

    Repository Management:
    - Clones repositories to /workspace/{repo_name} on first run
    - Pulls latest changes if already cloned
    - Checks out configured branch
    - Handles clone failures gracefully (errors logged, not blocking)

    State Isolation:
    - Pipeline locks use {project_id}:{board_id} namespace
    - Queue state uses {project_id}_{board_id}.yaml path
    - Session state uses {project_id}_workitem_{id}.yaml path
    - Workspace directories isolated per repository

    Example:
        async with service as svc:
            # Reload configurations (called each orchestration cycle)
            await svc.reload_config()

            # Get all enabled projects
            projects = await svc.get_enabled_projects()

            # For each enabled project:
            for project_name in projects:
                config = await svc.get_project_config(project_name)
                workspace = await svc.ensure_project_cloned(project_name)
                # Process project...
    """

    @abstractmethod
    async def get_enabled_projects(self) -> List[str]:
        """Return names of all enabled projects.

        Reads project configurations and filters to only those with
        enabled=True. Returns project names in a consistent order
        for deterministic processing.

        Returns:
            List[str]: Project names that are enabled (enabled=True).
                      Empty list if no projects are enabled.

        Raises:
            ExternalServiceError: Configuration service communication failure

        Example:
            >>> projects = await svc.get_enabled_projects()
            >>> print(projects)
            ['documentation_robotics', 'api_service']
        """
        pass

    @abstractmethod
    async def get_project_config(self, project_name: str) -> ProjectConfig:
        """Get configuration for a specific project.

        Retrieves the immutable ProjectConfig for the named project,
        including repository URL, branch, enabled status, and organization.

        Args:
            project_name: Name of the project to retrieve (e.g., "api-service")

        Returns:
            ProjectConfig: Immutable configuration for the project

        Raises:
            ResourceNotFoundError: Project configuration doesn't exist
            ExternalServiceError: Configuration service communication failure

        Example:
            >>> config = await svc.get_project_config("api-service")
            >>> print(config.repo_url)
            https://github.com/acme/api-service.git
        """
        pass

    @abstractmethod
    async def get_project_path(self, project_name: str) -> str:
        """Get workspace path for project (derived from repo URL).

        Derives the local workspace path where the project repository
        is or will be cloned. Path format: /workspace/{repo_name}

        The repository name is extracted from the repository URL by:
        1. Removing trailing ".git" suffix if present
        2. Taking the final path component

        Examples:
        - URL: "git@github.com:org/repo.git" → repo_name: "repo"
        - URL: "https://github.com/org/repo.git" → repo_name: "repo"
        - URL: "https://github.com/org/repo" → repo_name: "repo"

        Args:
            project_name: Name of the project

        Returns:
            str: Absolute path to workspace directory (e.g., "/workspace/api-service")

        Raises:
            ResourceNotFoundError: Project configuration doesn't exist
            ExternalServiceError: Configuration service communication failure

        Example:
            >>> path = await svc.get_project_path("api-service")
            >>> print(path)
            /workspace/api-service
        """
        pass

    @abstractmethod
    async def ensure_project_cloned(self, project_name: str) -> str:
        """Ensure project repository is cloned and up-to-date.

        Guarantees that the project repository is available at the
        workspace path. If the repository doesn't exist, it is cloned.
        If it exists, it is updated and checked out to the configured branch.

        Operations:
        1. Checks if repository already exists at workspace path
        2. If not: Clones the repository from repo_url to workspace
        3. If yes: Pulls latest changes from remote
        4. Checks out the configured branch
        5. Emits ProjectClonedEvent on success
        6. Emits ProjectCloneFailedEvent on transient errors (will retry next cycle)

        Clone failures are non-blocking. The service logs the error and emits
        an event, but processing continues to the next project. The next
        orchestration cycle will attempt the clone again.

        Args:
            project_name: Name of the project

        Returns:
            str: Absolute path to workspace directory where project is cloned

        Raises:
            ResourceNotFoundError: Project configuration doesn't exist
            ValidationError: Invalid repository URL or branch configuration
            ExternalServiceError: Repository clone/pull operation failed
                                 (transient - will retry next cycle)

        Events:
            - ProjectClonedEvent: Emitted on successful clone/pull
            - ProjectCloneFailedEvent: Emitted on transient errors

        Example:
            >>> workspace = await svc.ensure_project_cloned("api-service")
            >>> # Repository now available at workspace path
            >>> # Configured branch is checked out
        """
        pass

    @abstractmethod
    async def reload_config(self) -> None:
        """Reload project configurations from source.

        Re-reads project configurations (e.g., from projects.yaml file)
        to pick up any changes made since the last reload. Called at the
        beginning of each orchestration cycle to detect added, removed,
        or disabled projects.

        Subsequent calls to get_enabled_projects() and get_project_config()
        will reflect the newly loaded configuration.

        Configuration Changes Detected:
        - New projects added (emits ProjectEnabledEvent)
        - Projects disabled (emits ProjectDisabledEvent)
        - Repository URLs or branches changed
        - Projects removed from configuration

        Raises:
            ExternalServiceError: Configuration source read failure

        Example:
            >>> await svc.reload_config()  # Pick up changes from projects.yaml
            >>> projects = await svc.get_enabled_projects()  # Reflects new config
        """
        pass
