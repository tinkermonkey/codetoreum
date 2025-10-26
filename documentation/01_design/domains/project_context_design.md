# Project Context Domain Design

## Overview

Project Context is an aggregate root encapsulating project-specific configuration and context for workflow execution.

## Domain Model

```python
from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any
from datetime import datetime
from uuid import uuid4

@dataclass
class ProjectContext:
    """
    Project Context aggregate root.

    Encapsulates all project-specific configuration and settings.
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

    @classmethod
    def create(cls,
               name: str,
               display_name: str,
               repository_url: str,
               default_branch: str = "main",
               tech_stack: Optional[List[str]] = None,
               primary_language: str = "python",
               default_workflow_template_id: Optional[str] = None) -> 'ProjectContext':
        """Create new project context."""
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
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow()
        )

        event = ProjectContextCreated(
            aggregate_id=project.id,
            aggregate_type="ProjectContext",
            payload={
                "name": name,
                "repository_url": repository_url,
                "default_branch": default_branch
            }
        )
        project._add_event(event)

        return project

    def update_test_configuration(self,
                                  test_command: str,
                                  test_framework: Optional[str] = None) -> None:
        """Update testing configuration."""
        self.test_command = test_command
        self.test_framework = test_framework
        self.updated_at = datetime.utcnow()
        self._version += 1

        event = ProjectTestConfigUpdated(
            aggregate_id=self.id,
            aggregate_type="ProjectContext",
            payload={
                "test_command": test_command,
                "test_framework": test_framework
            }
        )
        self._add_event(event)

    def configure_docker(self,
                        has_dockerfile: bool,
                        dockerfile_path: Optional[str] = None,
                        requires_dev_container: bool = False) -> None:
        """Configure Docker settings."""
        self.has_dockerfile = has_dockerfile
        self.dockerfile_path = dockerfile_path
        self.requires_dev_container = requires_dev_container
        self.updated_at = datetime.utcnow()
        self._version += 1

    def add_custom_workflow(self, label: str, template_id: str) -> None:
        """Add custom workflow mapping for label."""
        self.custom_workflows[label] = template_id
        self.updated_at = datetime.utcnow()
        self._version += 1

    def get_workflow_template_for_labels(self, labels: List[str]) -> str:
        """Get workflow template ID based on labels."""
        for label in labels:
            if label in self.custom_workflows:
                return self.custom_workflows[label]
        return self.default_workflow_template_id

    def _add_event(self, event: DomainEvent) -> None:
        self._events.append(event)

    def get_pending_events(self) -> List[DomainEvent]:
        return self._events.copy()

    def clear_events(self) -> None:
        self._events.clear()
```

## Business Rules

1. Repository URL must be valid
2. Default branch must exist
3. Test command required if has_ci_cd is True
4. Dockerfile path required if has_dockerfile is True

## Domain Events

- **ProjectContextCreated**: Project initialized
- **ProjectTestConfigUpdated**: Test configuration changed
- **ProjectDockerConfigUpdated**: Docker settings changed
- **ProjectWorkflowMappingAdded**: Custom workflow added

## Integration

Used by:
- **WorkflowOrchestrator**: Select workflow template
- **AgentScheduler**: Configure execution environment
- **WorkspaceRouter**: Determine workspace type

## Testing

```python
def test_workflow_template_selection():
    project = ProjectContext.create(
        name="test-project",
        display_name="Test Project",
        repository_url="https://github.com/test/repo"
    )
    project.add_custom_workflow("hotfix", "hotfix-template")

    template_id = project.get_workflow_template_for_labels(["hotfix"])
    assert template_id == "hotfix-template"

    template_id = project.get_workflow_template_for_labels(["feature"])
    assert template_id == "default"
```

## References

- **Workflow Template**: `workflow_template_design.md`
- **Workspace Context**: `workspace_context_design.md`
