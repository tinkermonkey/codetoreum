"""Mock project manager service for testing multi-project orchestration.

This module provides a mock implementation of IProjectManagerService that stores
project configurations and state in memory without external dependencies. Used for
unit testing and simulation of multi-project workflows.

All project repository operations are simulated in-memory. Clone/pull operations
emit ProjectClonedEvent/ProjectCloneFailedEvent to track project availability.
Configuration changes emit ProjectEnabledEvent/ProjectDisabledEvent.
"""

import logging
import threading
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Dict, List, Optional, Set

from codetoreum.domain.events.project_events import (
    ProjectClonedEvent,
    ProjectCloneFailedEvent,
    ProjectDisabledEvent,
    ProjectEnabledEvent,
)
from codetoreum.domain.repository_url import extract_repo_name
from codetoreum.domain.value_objects import ProjectConfig
from codetoreum.domain.work_item import WorkItem
from codetoreum.ports.output.event_emitter import IEventEmitter
from codetoreum.ports.exceptions import (
    ExternalServiceError,
    ResourceNotFoundError,
    ValidationError,
)
from codetoreum.ports.output.project_manager_service import IProjectManagerService

logger = logging.getLogger(__name__)


@dataclass
class MockProjectState:
    """Internal state tracking for a project in the mock adapter.

    Attributes:
        config: The project configuration
        cloned: Whether the project has been successfully cloned
        clone_path: Path where the project is cloned
        last_clone_attempt: Timestamp of last clone attempt
        clone_failures: Count of consecutive clone failures
    """

    config: ProjectConfig
    cloned: bool = False
    clone_path: str = ""
    last_clone_attempt: Optional[datetime] = None
    clone_failures: int = 0


class MockProjectManagerAdapter(IProjectManagerService):
    """In-memory project manager for testing multi-project orchestration.

    Simulates project configuration management and repository operations
    without external dependencies. Emits events to track project lifecycle.

    Features:
    - Dictionary-based storage of project configurations
    - Simulated clone/pull operations
    - Event emission for configuration changes and clone status
    - Support for configuration reloading
    - Thread-safe for multi-threaded test scenarios (using threading.Lock)

    Note: Thread safety is limited to multi-threaded execution. Async methods
    on the same event loop share a thread, so concurrent coroutines require
    additional synchronization beyond threading.Lock. For async concurrency,
    use asyncio.Lock or similar async primitives.

    Example:
        # Setup
        adapter = MockProjectManagerAdapter(event_emitter=emitter)
        config = ProjectConfig(
            repo_url="https://github.com/acme/api-service.git",
            branch="main",
            enabled=True,
            org="acme"
        )
        adapter.add_project("api-service", config)

        # Get enabled projects
        projects = await adapter.get_enabled_projects()
        assert "api-service" in projects

        # Ensure cloned
        path = await adapter.ensure_project_cloned("api-service")
        assert path == "/workspace/api-service"

        # Verify event was emitted
        events = emitter.get_emitted_events()
        assert any(isinstance(e, ProjectClonedEvent) for e in events)
    """

    def __init__(
        self,
        event_emitter: Optional[IEventEmitter] = None,
        base_workspace: str = "/workspace",
    ) -> None:
        """Initialize the mock project manager adapter.

        Args:
            event_emitter: Optional event emitter for emitting project events.
                          If not provided, events are not emitted.
            base_workspace: Base path for cloned projects (default: /workspace)
        """
        self._projects: Dict[str, MockProjectState] = {}
        self._event_emitter = event_emitter
        self._base_workspace = base_workspace
        self._lock = threading.Lock()
        self._clone_failures: Set[str] = set()  # Per-project clone failures
        self._project_boards: Dict[str, List[str]] = {}  # Per-project boards
        self._project_work_items: Dict[str, List[WorkItem]] = {}  # Per-project work items

    # =========================================================================
    # IProjectManagerService Implementation
    # =========================================================================

    async def get_enabled_projects(self) -> List[str]:
        """Return names of all enabled projects.

        Returns only projects with enabled=True in their configuration.
        Results are sorted for deterministic ordering.

        Returns:
            List[str]: Sorted list of enabled project names

        Raises:
            ExternalServiceError: Should not occur in mock implementation
        """
        with self._lock:
            enabled = [
                name
                for name, state in self._projects.items()
                if state.config.enabled
            ]
            return sorted(enabled)

    async def get_project_config(self, project_name: str) -> ProjectConfig:
        """Get configuration for a specific project.

        Args:
            project_name: Name of the project

        Returns:
            ProjectConfig: Immutable configuration for the project

        Raises:
            ResourceNotFoundError: Project configuration doesn't exist
        """
        with self._lock:
            if project_name not in self._projects:
                raise ResourceNotFoundError("Project", project_name)
            return self._projects[project_name].config

    async def get_project_path(self, project_name: str) -> str:
        """Get workspace path for project (derived from repo URL).

        Derives the local workspace path by extracting the repository name
        from the repo URL (removing .git suffix and taking final path component).

        Examples:
        - URL: "git@github.com:org/repo.git" → "/workspace/repo"
        - URL: "https://github.com/org/repo.git" → "/workspace/repo"
        - URL: "https://github.com/org/repo" → "/workspace/repo"

        Args:
            project_name: Name of the project

        Returns:
            str: Absolute path to workspace directory

        Raises:
            ResourceNotFoundError: Project configuration doesn't exist
        """
        with self._lock:
            if project_name not in self._projects:
                raise ResourceNotFoundError("Project", project_name)

            config = self._projects[project_name].config
            repo_url = config.repo_url
            repo_name = extract_repo_name(repo_url)
            return f"{self._base_workspace}/{repo_name}"

    async def ensure_project_cloned(self, project_name: str) -> str:
        """Ensure project repository is cloned and up-to-date.

        In the mock implementation, this simulates the clone operation
        and emits ProjectClonedEvent or ProjectCloneFailedEvent.

        Operations:
        1. Verifies project configuration exists
        2. Derives workspace path from repo URL
        3. Marks project as cloned
        4. Emits ProjectClonedEvent on success
        5. Emits ProjectCloneFailedEvent on simulated failures

        Args:
            project_name: Name of the project

        Returns:
            str: Absolute path to workspace directory

        Raises:
            ResourceNotFoundError: Project configuration doesn't exist
            ValidationError: Invalid repository URL
            ExternalServiceError: Clone failed (transient error)
        """
        with self._lock:
            if project_name not in self._projects:
                raise ResourceNotFoundError("Project", project_name)

            state = self._projects[project_name]
            config = state.config
            workspace_path = f"{self._base_workspace}/{extract_repo_name(config.repo_url)}"

            # Simulate clone failure if project in clone_failures set
            if project_name in self._clone_failures:
                state.clone_failures += 1
                event = ProjectCloneFailedEvent(
                    type="project.clone_failed",
                    timestamp=self._get_iso_timestamp(),
                    source="mock_project_manager",
                    project_name=project_name,
                    repo_url=config.repo_url,
                    error_message="Simulated transient error: network timeout",
                    will_retry=True,
                )
                if self._event_emitter:
                    self._event_emitter.emit(event)
                raise ExternalServiceError(
                    "mock_project_manager",
                    f"Failed to clone project '{project_name}': simulated network timeout"
                )

            # Mark as cloned
            state.cloned = True
            state.clone_path = workspace_path
            state.last_clone_attempt = datetime.now(timezone.utc)
            state.clone_failures = 0

            # Emit success event
            event = ProjectClonedEvent(
                type="project.cloned",
                timestamp=self._get_iso_timestamp(),
                source="mock_project_manager",
                project_name=project_name,
                repo_url=config.repo_url,
                workspace_path=workspace_path,
                branch=config.branch,
            )
            if self._event_emitter:
                self._event_emitter.emit(event)

            return workspace_path

    async def reload_config(self) -> None:
        """Reload project configurations from source.

        In the mock implementation, this is a no-op since configurations
        are managed in-memory. Projects can be added/modified via
        helper methods like add_project() and update_project().

        In a real implementation, this would re-read from projects.yaml
        and emit ProjectEnabledEvent/ProjectDisabledEvent for changes.

        Raises:
            ExternalServiceError: Configuration source read failure
        """
        # In mock implementation, configurations are managed via helper methods
        # This is a no-op
        pass

    # =========================================================================
    # Test Helper Methods
    # =========================================================================

    def add_project(self, project_name: str, config: ProjectConfig) -> None:
        """Add a project configuration for testing.

        Args:
            project_name: Name of the project
            config: Project configuration
        """
        with self._lock:
            if project_name in self._projects:
                raise ValueError(f"Project {project_name} already exists")
            self._projects[project_name] = MockProjectState(config=config)

    def update_project(self, project_name: str, config: ProjectConfig) -> None:
        """Update a project configuration.

        Args:
            project_name: Name of the project
            config: New project configuration

        Raises:
            ResourceNotFoundError: Project doesn't exist
        """
        with self._lock:
            if project_name not in self._projects:
                raise ResourceNotFoundError("Project", project_name)
            self._projects[project_name].config = config

    def remove_project(self, project_name: str) -> None:
        """Remove a project configuration.

        Args:
            project_name: Name of the project

        Raises:
            ResourceNotFoundError: Project doesn't exist
        """
        with self._lock:
            if project_name not in self._projects:
                raise ResourceNotFoundError("Project", project_name)
            del self._projects[project_name]

    def get_project_state(self, project_name: str) -> Optional[MockProjectState]:
        """Get internal state for a project (testing only).

        Args:
            project_name: Name of the project

        Returns:
            MockProjectState if found, None otherwise
        """
        with self._lock:
            return self._projects.get(project_name)

    def clear(self) -> None:
        """Clear all project configurations (testing cleanup)."""
        with self._lock:
            self._projects.clear()

    def simulate_clone_failure(self, project_name: str) -> None:
        """Simulate clone failure for a specific project for testing.

        When a project is in the clone failures set, ensure_project_cloned()
        will fail with ProjectCloneFailedEvent emission and ExternalServiceError.

        Args:
            project_name: Name of the project to simulate clone failure for
        """
        with self._lock:
            self._clone_failures.add(project_name)

    def clear_clone_failure(self, project_name: str) -> None:
        """Clear simulated clone failure for a specific project.

        Args:
            project_name: Name of the project
        """
        with self._lock:
            self._clone_failures.discard(project_name)

    def add_work_item_to_project(
        self, project_name: str, work_item: WorkItem
    ) -> None:
        """Add a work item to a project for simulation testing.

        Args:
            project_name: Name of the project
            work_item: Work item to add

        Raises:
            ResourceNotFoundError: Project doesn't exist
        """
        with self._lock:
            if project_name not in self._projects:
                raise ResourceNotFoundError("Project", project_name)
            if project_name not in self._project_work_items:
                self._project_work_items[project_name] = []
            self._project_work_items[project_name].append(work_item)

    def add_boards_to_project(self, project_name: str, boards: List[str]) -> None:
        """Configure boards for a project.

        Args:
            project_name: Name of the project
            boards: List of board names

        Raises:
            ResourceNotFoundError: Project doesn't exist
        """
        with self._lock:
            if project_name not in self._projects:
                raise ResourceNotFoundError("Project", project_name)
            self._project_boards[project_name] = boards

    def get_project_boards(self, project_name: str) -> List[str]:
        """Get boards configured for a project.

        Args:
            project_name: Name of the project

        Returns:
            List of board names for the project

        Raises:
            ResourceNotFoundError: Project doesn't exist
        """
        with self._lock:
            if project_name not in self._projects:
                raise ResourceNotFoundError("Project", project_name)
            return self._project_boards.get(project_name, [])

    def get_project_work_items(self, project_name: str) -> List[WorkItem]:
        """Get work items added to a project.

        Args:
            project_name: Name of the project

        Returns:
            List of work items for the project

        Raises:
            ResourceNotFoundError: Project doesn't exist
        """
        with self._lock:
            if project_name not in self._projects:
                raise ResourceNotFoundError("Project", project_name)
            return self._project_work_items.get(project_name, []).copy()

    def get_clone_failure_count(self, project_name: str) -> int:
        """Get count of clone failures for a project.

        Args:
            project_name: Name of the project

        Returns:
            Number of consecutive clone failures

        Raises:
            ResourceNotFoundError: Project doesn't exist
        """
        with self._lock:
            if project_name not in self._projects:
                raise ResourceNotFoundError("Project", project_name)
            return self._projects[project_name].clone_failures

    def set_event_emitter(self, event_emitter: IEventEmitter) -> None:
        """Set or update the event emitter.

        Args:
            event_emitter: Event emitter for project events
        """
        with self._lock:
            self._event_emitter = event_emitter

    # =========================================================================
    # Private Methods
    # =========================================================================

    @staticmethod
    def _get_iso_timestamp() -> str:
        """Get current timestamp in ISO 8601 format with UTC timezone.

        Returns:
            ISO 8601 timestamp string
        """
        return datetime.now(timezone.utc).isoformat()
