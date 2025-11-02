"""Project Context aggregate root."""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from uuid import uuid4

from codetoreum.domain.events import DomainEvent
from codetoreum.domain.exceptions import DomainError


# =============================================================================
# Project Context Events
# =============================================================================


class ProjectContextCreated(DomainEvent):
    """Emitted when project context is created."""

    def __init__(self, aggregate_id: str, payload: Dict[str, Any], **kwargs):
        """
        Initialize ProjectContextCreated event.

        Required payload fields:
        - name: str
        - repository_url: str
        - default_branch: str
        """
        super().__init__(
            aggregate_id=aggregate_id,
            aggregate_type="ProjectContext",
            payload=payload,
            **kwargs
        )


class ProjectTestConfigUpdated(DomainEvent):
    """Emitted when test configuration is updated."""

    def __init__(self, aggregate_id: str, payload: Dict[str, Any], **kwargs):
        """
        Initialize ProjectTestConfigUpdated event.

        Required payload fields:
        - test_command: str
        - test_framework: Optional[str]
        """
        super().__init__(
            aggregate_id=aggregate_id,
            aggregate_type="ProjectContext",
            payload=payload,
            **kwargs
        )


class ProjectDockerConfigUpdated(DomainEvent):
    """Emitted when Docker configuration is updated."""

    def __init__(self, aggregate_id: str, payload: Dict[str, Any], **kwargs):
        """
        Initialize ProjectDockerConfigUpdated event.

        Required payload fields:
        - has_dockerfile: bool
        - dockerfile_path: Optional[str]
        - requires_dev_container: bool
        """
        super().__init__(
            aggregate_id=aggregate_id,
            aggregate_type="ProjectContext",
            payload=payload,
            **kwargs
        )


class ProjectWorkflowMappingAdded(DomainEvent):
    """Emitted when custom workflow mapping is added."""

    def __init__(self, aggregate_id: str, payload: Dict[str, Any], **kwargs):
        """
        Initialize ProjectWorkflowMappingAdded event.

        Required payload fields:
        - label: str
        - template_id: str
        """
        super().__init__(
            aggregate_id=aggregate_id,
            aggregate_type="ProjectContext",
            payload=payload,
            **kwargs
        )


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
    tech_stack: List[str]
    primary_language: str

    # Testing configuration
    test_command: Optional[str]
    test_framework: Optional[str]
    has_ci_cd: bool

    # Workflow configuration
    default_workflow_template_id: str
    custom_workflows: Dict[str, str]  # label -> template_id

    # Docker configuration
    has_dockerfile: bool
    dockerfile_path: Optional[str]
    requires_dev_container: bool

    # Environment
    environment_variables: Dict[str, str]
    secrets: List[str]  # Names of required secrets

    # MCP servers
    mcp_servers: List[str]

    # Metadata
    metadata: Dict[str, Any]

    # Timestamps
    created_at: datetime
    updated_at: datetime

    # Event tracking
    _events: List[DomainEvent] = field(default_factory=list, init=False, repr=False)
    _version: int = field(default=0, init=False, repr=False)

    def __post_init__(self):
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
            raise DomainError("Project context must have a non-empty name")

        if not self.repository_url or not self.repository_url.strip():
            raise DomainError("Project context must have a repository URL")

        if not self.default_branch or not self.default_branch.strip():
            raise DomainError("Project context must have a default branch")

        if self.has_dockerfile and not self.dockerfile_path:
            raise DomainError("Dockerfile path required when has_dockerfile is True")

    # Creation
    @classmethod
    def create(
        cls,
        name: str,
        display_name: str,
        repository_url: str,
        default_branch: str = "main",
        tech_stack: Optional[List[str]] = None,
        primary_language: str = "python",
        default_workflow_template_id: Optional[str] = None
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
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc)
        )

        event = ProjectContextCreated(
            aggregate_id=project.id,
            payload={
                "name": name,
                "display_name": display_name,
                "repository_url": repository_url,
                "default_branch": default_branch,
                "primary_language": primary_language
            }
        )
        project._add_event(event)

        return project

    # Configuration methods
    def update_test_configuration(
        self,
        test_command: str,
        test_framework: Optional[str] = None
    ) -> None:
        """
        Update testing configuration.

        Args:
            test_command: Command to run tests
            test_framework: Test framework name (optional)

        Emits: ProjectTestConfigUpdated event
        """
        if not test_command or not test_command.strip():
            raise DomainError("Test command cannot be empty")

        self.test_command = test_command
        self.test_framework = test_framework
        self.updated_at = datetime.now(timezone.utc)
        self._version += 1

        event = ProjectTestConfigUpdated(
            aggregate_id=self.id,
            payload={
                "test_command": test_command,
                "test_framework": test_framework
            }
        )
        self._add_event(event)

    def configure_docker(
        self,
        has_dockerfile: bool,
        dockerfile_path: Optional[str] = None,
        requires_dev_container: bool = False
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
            raise DomainError("Dockerfile path required when has_dockerfile is True")

        self.has_dockerfile = has_dockerfile
        self.dockerfile_path = dockerfile_path
        self.requires_dev_container = requires_dev_container
        self.updated_at = datetime.now(timezone.utc)
        self._version += 1

        event = ProjectDockerConfigUpdated(
            aggregate_id=self.id,
            payload={
                "has_dockerfile": has_dockerfile,
                "dockerfile_path": dockerfile_path,
                "requires_dev_container": requires_dev_container
            }
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
            raise DomainError("Label cannot be empty")

        if not template_id or not template_id.strip():
            raise DomainError("Template ID cannot be empty")

        self.custom_workflows[label] = template_id
        self.updated_at = datetime.now(timezone.utc)
        self._version += 1

        event = ProjectWorkflowMappingAdded(
            aggregate_id=self.id,
            payload={
                "label": label,
                "template_id": template_id
            }
        )
        self._add_event(event)

    def get_workflow_template_for_labels(self, labels: List[str]) -> str:
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
    def _add_event(self, event: DomainEvent) -> None:
        """
        Add event to pending events list.

        Args:
            event: Domain event to add
        """
        self._events.append(event)

    def get_pending_events(self) -> List[DomainEvent]:
        """
        Get all pending events.

        Returns:
            Copy of the pending events list
        """
        return list(self._events)

    def clear_events(self) -> None:
        """Clear pending events (after persistence)."""
        self._events.clear()
