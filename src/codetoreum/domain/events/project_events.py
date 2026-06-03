"""Project lifecycle events for multi-project orchestration.

Events track changes to project configurations, repository states, and
orchestration cycle completions. These immutable events form the audit
trail for multi-project management operations.

All events use frozen dataclasses to ensure immutability for proper
event sourcing.
"""

from dataclasses import dataclass
from typing import Any
from uuid import uuid4

from .adapter_events import CodetoreumEvent


@dataclass(frozen=True)
class ProjectClonedEvent(CodetoreumEvent):
    """Emitted when a project repository is successfully cloned or updated.

    See module docstring for immutability guarantees.

    Fired when:
    - A repository is cloned for the first time to the workspace
    - An existing repository is pulled to update with latest changes
    - The configured branch is checked out successfully

    This event indicates that the project repository is now available and
    ready for agent execution (work item processing).

    Attributes:
        type (str): Fixed to "project.cloned"
        project_name (str): Name of the project (e.g., "api-service")
        repo_url (str): Repository URL that was cloned
        workspace_path (str): Absolute path where repository is available
        branch (str): Branch that is checked out

    Example:
        >>> event = ProjectClonedEvent(
        ...     type="project.cloned",
        ...     timestamp="2025-02-08T10:30:00+00:00",
        ...     source="project_manager",
        ...     project_name="api-service",
        ...     repo_url="https://github.com/acme/api-service.git",
        ...     workspace_path="/workspace/api-service",
        ...     branch="main"
        ... )
        >>> event.workspace_path = "/workspace/other"  # ❌ Raises FrozenInstanceError
    """

    project_name: str = ""
    repo_url: str = ""
    workspace_path: str = ""
    branch: str = ""

    def __post_init__(self) -> None:
        """Validate event after initialization."""
        super().__post_init__()
        if not self.project_name:
            msg = "project_name is required"
            raise ValueError(msg)
        if not self.repo_url:
            msg = "repo_url is required"
            raise ValueError(msg)
        if not self.workspace_path:
            msg = "workspace_path is required"
            raise ValueError(msg)
        if not self.branch:
            msg = "branch is required"
            raise ValueError(msg)

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dictionary."""
        d = super().to_dict()
        d.update(
            {
                "project_name": self.project_name,
                "repo_url": self.repo_url,
                "workspace_path": self.workspace_path,
                "branch": self.branch,
            }
        )
        return d

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ProjectClonedEvent":
        """Deserialize from dictionary.

        Raises:
            ValueError: If required fields are missing from input dict
        """
        missing_fields = []
        for field in ["project_name", "repo_url", "workspace_path", "branch"]:
            if not data.get(field):
                missing_fields.append(field)

        if missing_fields:
            msg = (
                f"Cannot deserialize ProjectClonedEvent: missing required field(s) "
                f"{missing_fields}. All of project_name, repo_url, workspace_path, "
                f"and branch are required."
            )
            raise ValueError(msg)

        return cls(
            type=data.get("type", "project.cloned"),
            timestamp=data.get("timestamp", ""),
            source=data.get("source", ""),
            correlation_id=data.get("correlation_id"),
            event_id=data.get("event_id") or str(uuid4()),
            project_name=data.get("project_name", ""),
            repo_url=data.get("repo_url", ""),
            workspace_path=data.get("workspace_path", ""),
            branch=data.get("branch", ""),
        )


@dataclass(frozen=True)
class ProjectCloneFailedEvent(CodetoreumEvent):
    """Emitted when a project clone or update fails with a transient error.

    See module docstring for immutability guarantees.

    Fired when:
    - Repository clone fails (network issues, temporary service outage)
    - Repository pull fails (network issues, merge conflicts)
    - Branch checkout fails (temporary issues)

    Clone failures are transient and non-blocking. Processing continues
    to the next project, and the orchestrator will retry the clone in the
    next orchestration cycle. Permanent errors (invalid URL, authentication)
    are raised as exceptions instead of emitting this event.

    Attributes:
        type (str): Fixed to "project.clone_failed"
        project_name (str): Name of the project that failed to clone
        repo_url (str): Repository URL that was being cloned
        error_message (str): Description of the error that occurred
        will_retry (bool): Whether the clone will be retried in the next cycle

    Example:
        >>> event = ProjectCloneFailedEvent(
        ...     type="project.clone_failed",
        ...     timestamp="2025-02-08T10:30:00+00:00",
        ...     source="project_manager",
        ...     project_name="api-service",
        ...     repo_url="https://github.com/acme/api-service.git",
        ...     error_message="Connection timeout: Could not reach github.com",
        ...     will_retry=True
        ... )
    """

    project_name: str = ""
    repo_url: str = ""
    error_message: str = ""
    will_retry: bool = True

    def __post_init__(self) -> None:
        """Validate event after initialization."""
        super().__post_init__()
        if not self.project_name:
            msg = "project_name is required"
            raise ValueError(msg)
        if not self.repo_url:
            msg = "repo_url is required"
            raise ValueError(msg)
        if not self.error_message:
            msg = "error_message is required"
            raise ValueError(msg)

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dictionary."""
        d = super().to_dict()
        d.update(
            {
                "project_name": self.project_name,
                "repo_url": self.repo_url,
                "error_message": self.error_message,
                "will_retry": self.will_retry,
            }
        )
        return d

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ProjectCloneFailedEvent":
        """Deserialize from dictionary.

        Raises:
            ValueError: If required fields are missing from input dict
        """
        missing_fields = []
        for field in ["project_name", "repo_url", "error_message"]:
            if not data.get(field):
                missing_fields.append(field)

        if missing_fields:
            msg = (
                f"Cannot deserialize ProjectCloneFailedEvent: missing required field(s) "
                f"{missing_fields}. All of project_name, repo_url, and error_message "
                f"are required."
            )
            raise ValueError(msg)

        return cls(
            type=data.get("type", "project.clone_failed"),
            timestamp=data.get("timestamp", ""),
            source=data.get("source", ""),
            correlation_id=data.get("correlation_id"),
            event_id=data.get("event_id") or str(uuid4()),
            project_name=data.get("project_name", ""),
            repo_url=data.get("repo_url", ""),
            error_message=data.get("error_message", ""),
            will_retry=data.get("will_retry", True),
        )


@dataclass(frozen=True)
class ProjectEnabledEvent(CodetoreumEvent):
    """Emitted when a project becomes enabled in configuration.

    See module docstring for immutability guarantees.

    Fired when:
    - A project's enabled status changes from false to true
    - Configuration is reloaded and a previously disabled project is now enabled
    - A new project is added to configuration with enabled=true

    Indicates that the project will be included in the next orchestration cycle.

    Attributes:
        type (str): Fixed to "project.enabled"
        project_name (str): Name of the project that became enabled

    Example:
        >>> event = ProjectEnabledEvent(
        ...     type="project.enabled",
        ...     timestamp="2025-02-08T10:30:00+00:00",
        ...     source="project_manager",
        ...     project_name="api-service"
        ... )
    """

    project_name: str = ""

    def __post_init__(self) -> None:
        """Validate event after initialization."""
        super().__post_init__()
        if not self.project_name:
            msg = "project_name is required"
            raise ValueError(msg)

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dictionary."""
        d = super().to_dict()
        d.update(
            {
                "project_name": self.project_name,
            }
        )
        return d

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ProjectEnabledEvent":
        """Deserialize from dictionary.

        Raises:
            ValueError: If required fields are missing from input dict
        """
        if not data.get("project_name"):
            msg = "Cannot deserialize ProjectEnabledEvent: missing required field 'project_name'"
            raise ValueError(msg)

        return cls(
            type=data.get("type", "project.enabled"),
            timestamp=data.get("timestamp", ""),
            source=data.get("source", ""),
            correlation_id=data.get("correlation_id"),
            event_id=data.get("event_id") or str(uuid4()),
            project_name=data.get("project_name", ""),
        )


@dataclass(frozen=True)
class ProjectDisabledEvent(CodetoreumEvent):
    """Emitted when a project becomes disabled in configuration.

    See module docstring for immutability guarantees.

    Fired when:
    - A project's enabled status changes from true to false
    - Configuration is reloaded and a previously enabled project is now disabled
    - A project is removed from configuration

    Indicates that the project will be excluded from the next orchestration cycle.

    Attributes:
        type (str): Fixed to "project.disabled"
        project_name (str): Name of the project that became disabled

    Example:
        >>> event = ProjectDisabledEvent(
        ...     type="project.disabled",
        ...     timestamp="2025-02-08T10:30:00+00:00",
        ...     source="project_manager",
        ...     project_name="deprecated-service"
        ... )
    """

    project_name: str = ""

    def __post_init__(self) -> None:
        """Validate event after initialization."""
        super().__post_init__()
        if not self.project_name:
            msg = "project_name is required"
            raise ValueError(msg)

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dictionary."""
        d = super().to_dict()
        d.update(
            {
                "project_name": self.project_name,
            }
        )
        return d

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ProjectDisabledEvent":
        """Deserialize from dictionary.

        Raises:
            ValueError: If required fields are missing from input dict
        """
        if not data.get("project_name"):
            msg = "Cannot deserialize ProjectDisabledEvent: missing required field 'project_name'"
            raise ValueError(msg)

        return cls(
            type=data.get("type", "project.disabled"),
            timestamp=data.get("timestamp", ""),
            source=data.get("source", ""),
            correlation_id=data.get("correlation_id"),
            event_id=data.get("event_id") or str(uuid4()),
            project_name=data.get("project_name", ""),
        )


