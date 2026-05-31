"""Project Context aggregate root."""

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from codetoreum.domain.events.adapter_events import now_iso
from codetoreum.domain.events.project_context_events import (
    ProjectContextCreatedEvent,
    ProjectDockerConfigUpdatedEvent,
    ProjectTestConfigUpdatedEvent,
    ProjectWorkflowMappingAddedEvent,
)
from codetoreum.domain.exceptions import DomainError

# =============================================================================
# Project Context Aggregate
# =============================================================================


@dataclass
class ProjectContext:
    """
    Project Context aggregate root.

    Encapsulates all project-specific configuration and settings.
    This is an aggregate root that manages project configuration,
    workflow templates, Docker settings, and environment variables.
    """

    # Identity
    id: str
    name: str
    display_name: str

    # Repository
    repository_url: str
    default_branch: str
    branch_prefix: str

    # Technology stack
    tech_stack: list[str]
    primary_language: str

    # Testing configuration
    test_command: str | None
    test_framework: str | None
    has_ci_cd: bool

    # Workflow configuration
    default_workflow_template_id: str
    custom_workflows: dict[str, str]  # label -> template_id

    # Docker configuration
    has_dockerfile: bool
    dockerfile_path: str | None
    requires_dev_container: bool

    # Environment
    environment_variables: dict[str, str]
    secrets: list[str]  # Names of required secrets

    # MCP servers
    mcp_servers: list[str]

    # Metadata
    metadata: dict[str, Any]

    # Timestamps
    created_at: datetime
    updated_at: datetime

    # Workflow integrations
    # When True (default), the executor calls
    # ``IVersionControlService.create_pull_request`` after a successful
    # agent push. Disable per-project to keep the head branch unreviewed
    # (e.g. a project that ships through a different review surface).
    auto_create_pull_requests: bool = True

    # Event tracking
    _events: list = field(default_factory=list, init=False, repr=False)
    _version: int = field(default=0, init=False, repr=False)

    def __post_init__(self) -> None:
        """Validate invariants after initialization."""
        self._validate_invariants()

    def _validate_invariants(self) -> None:
        """
        Validate domain invariants.

        Invariants:
        - Name must be non-empty
        - Repository URL must be non-empty
        - Default branch must be non-empty
        - If has_dockerfile is True, dockerfile_path must be set
        - If has_ci_cd is True, test_command should be set
        """
        if not self.name or not self.name.strip():
            msg = "Project context must have a non-empty name"
            raise DomainError(msg)

        if not self.repository_url or not self.repository_url.strip():
            msg = "Project context must have a repository URL"
            raise DomainError(msg)

        if not self.default_branch or not self.default_branch.strip():
            msg = "Project context must have a default branch"
            raise DomainError(msg)

        if self.has_dockerfile and not self.dockerfile_path:
            msg = "Dockerfile path required when has_dockerfile is True"
            raise DomainError(msg)

    # Creation
    @classmethod
    def create(
        cls,
        name: str,
        display_name: str,
        repository_url: str,
        default_branch: str = "main",
        tech_stack: list[str] | None = None,
        primary_language: str = "python",
        default_workflow_template_id: str | None = None,
    ) -> "ProjectContext":
        """
        Factory method to create a new project context.

        Args:
            name: Project name (identifier)
            display_name: Human-readable project name
            repository_url: Git repository URL
            default_branch: Default branch (defaults to "main")
            tech_stack: List of technologies used in project
            primary_language: Primary programming language
            default_workflow_template_id: Default workflow template to use

        Returns:
            Newly created ProjectContext instance

        Emits: ProjectContextCreated event
        """
        project = cls(
            id=str(uuid4()),
            name=name,
            display_name=display_name,
            repository_url=repository_url,
            default_branch=default_branch,
            branch_prefix="feature/",
            tech_stack=tech_stack or [],
            primary_language=primary_language,
            test_command=None,
            test_framework=None,
            has_ci_cd=False,
            default_workflow_template_id=default_workflow_template_id or "default",
            custom_workflows={},
            has_dockerfile=False,
            dockerfile_path=None,
            requires_dev_container=False,
            environment_variables={},
            secrets=[],
            mcp_servers=[],
            metadata={},
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )

        event = ProjectContextCreatedEvent(
            type="project_context.created",
            timestamp=now_iso(),
            source="domain",
            project_id=project.id,
            name=name,
        )
        project._add_event(event)

        return project

    # Configuration methods
    def update_test_configuration(self, test_command: str, test_framework: str | None = None) -> None:
        """
        Update testing configuration.

        Args:
            test_command: Command to run tests
            test_framework: Test framework name (optional)

        Emits: ProjectTestConfigUpdated event
        """
        if not test_command or not test_command.strip():
            msg = "Test command cannot be empty"
            raise DomainError(msg)

        self.test_command = test_command
        self.test_framework = test_framework
        self.updated_at = datetime.now(UTC)
        self._version += 1

        event = ProjectTestConfigUpdatedEvent(
            type="project_context.test_config_updated",
            timestamp=now_iso(),
            source="domain",
            project_id=self.id,
            test_command=test_command or "",
        )
        self._add_event(event)

    def configure_docker(
        self,
        has_dockerfile: bool,
        dockerfile_path: str | None = None,
        requires_dev_container: bool = False,
    ) -> None:
        """
        Configure Docker settings.

        Args:
            has_dockerfile: Whether project has a Dockerfile
            dockerfile_path: Path to Dockerfile (required if has_dockerfile is True)
            requires_dev_container: Whether project requires dev container

        Raises:
            DomainError: If has_dockerfile is True but dockerfile_path is not provided

        Emits: ProjectDockerConfigUpdated event
        """
        if has_dockerfile and not dockerfile_path:
            msg = "Dockerfile path required when has_dockerfile is True"
            raise DomainError(msg)

        self.has_dockerfile = has_dockerfile
        self.dockerfile_path = dockerfile_path
        self.requires_dev_container = requires_dev_container
        self.updated_at = datetime.now(UTC)
        self._version += 1

        event = ProjectDockerConfigUpdatedEvent(
            type="project_context.docker_config_updated",
            timestamp=now_iso(),
            source="domain",
            project_id=self.id,
            image=dockerfile_path or "",
        )
        self._add_event(event)

    def add_custom_workflow(self, label: str, template_id: str) -> None:
        """
        Add custom workflow mapping for label.

        Args:
            label: Label to match on work items
            template_id: Workflow template ID to use for this label

        Raises:
            DomainError: If label or template_id is empty

        Emits: ProjectWorkflowMappingAdded event
        """
        if not label or not label.strip():
            msg = "Label cannot be empty"
            raise DomainError(msg)

        if not template_id or not template_id.strip():
            msg = "Template ID cannot be empty"
            raise DomainError(msg)

        self.custom_workflows[label] = template_id
        self.updated_at = datetime.now(UTC)
        self._version += 1

        event = ProjectWorkflowMappingAddedEvent(
            type="project_context.workflow_mapping_added",
            timestamp=now_iso(),
            source="domain",
            project_id=self.id,
            column_name=label,
            workflow_stage=template_id,
        )
        self._add_event(event)

    def get_workflow_template_for_labels(self, labels: list[str]) -> str:
        """
        Get workflow template ID based on work item labels.

        Checks labels in order and returns the first matching custom workflow.
        Falls back to default workflow template if no match found.

        Args:
            labels: List of labels from work item

        Returns:
            Workflow template ID to use
        """
        for label in labels:
            if label in self.custom_workflows:
                return self.custom_workflows[label]
        return self.default_workflow_template_id

    # Event management
    def _add_event(self, event: object) -> None:
        """
        Add event to pending events list.

        Args:
            event: Domain event to add
        """
        self._events.append(event)

    def get_pending_events(self) -> list:
        """
        Get all pending events.

        Returns:
            Copy of the pending events list
        """
        return list(self._events)

    def clear_events(self) -> None:
        """Clear pending events (after persistence)."""
        self._events.clear()
