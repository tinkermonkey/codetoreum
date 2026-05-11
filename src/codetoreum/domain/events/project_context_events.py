"""Project context domain events using frozen dataclasses."""

from dataclasses import dataclass

from .adapter_events import CodetoreumEvent


@dataclass(frozen=True)
class ProjectContextCreatedEvent(CodetoreumEvent):
    """Emitted when a project context is created."""

    project_id: str = ""
    name: str = ""

    def __post_init__(self) -> None:
        super().__post_init__()
        if not self.project_id:
            raise ValueError("project_id is required")

    def to_dict(self) -> dict:
        d = super().to_dict()
        d.update({"project_id": self.project_id, "name": self.name})
        return d

    @classmethod
    def from_dict(cls, data: dict) -> "ProjectContextCreatedEvent":
        return cls(
            type=data.get("type", "ProjectContextCreatedEvent"),
            timestamp=data.get("timestamp", ""),
            source=data.get("source", ""),
            correlation_id=data.get("correlation_id", ""),
            event_id=data.get("event_id", ""),
            project_id=data.get("project_id", ""),
            name=data.get("name", ""),
        )


@dataclass(frozen=True)
class ProjectTestConfigUpdatedEvent(CodetoreumEvent):
    """Emitted when a project test config is updated."""

    project_id: str = ""
    test_command: str = ""
    test_timeout: int = 0

    def __post_init__(self) -> None:
        super().__post_init__()
        if not self.project_id:
            raise ValueError("project_id is required")

    def to_dict(self) -> dict:
        d = super().to_dict()
        d.update({"project_id": self.project_id, "test_command": self.test_command, "test_timeout": self.test_timeout})
        return d

    @classmethod
    def from_dict(cls, data: dict) -> "ProjectTestConfigUpdatedEvent":
        return cls(
            type=data.get("type", "ProjectTestConfigUpdatedEvent"),
            timestamp=data.get("timestamp", ""),
            source=data.get("source", ""),
            correlation_id=data.get("correlation_id", ""),
            event_id=data.get("event_id", ""),
            project_id=data.get("project_id", ""),
            test_command=data.get("test_command", ""),
            test_timeout=data.get("test_timeout", 0),
        )


@dataclass(frozen=True)
class ProjectDockerConfigUpdatedEvent(CodetoreumEvent):
    """Emitted when a project docker config is updated."""

    project_id: str = ""
    image: str = ""

    def __post_init__(self) -> None:
        super().__post_init__()
        if not self.project_id:
            raise ValueError("project_id is required")

    def to_dict(self) -> dict:
        d = super().to_dict()
        d.update({"project_id": self.project_id, "image": self.image})
        return d

    @classmethod
    def from_dict(cls, data: dict) -> "ProjectDockerConfigUpdatedEvent":
        return cls(
            type=data.get("type", "ProjectDockerConfigUpdatedEvent"),
            timestamp=data.get("timestamp", ""),
            source=data.get("source", ""),
            correlation_id=data.get("correlation_id", ""),
            event_id=data.get("event_id", ""),
            project_id=data.get("project_id", ""),
            image=data.get("image", ""),
        )


@dataclass(frozen=True)
class ProjectWorkflowMappingAddedEvent(CodetoreumEvent):
    """Emitted when a workflow mapping is added to a project context."""

    project_id: str = ""
    column_name: str = ""
    workflow_stage: str = ""

    def __post_init__(self) -> None:
        super().__post_init__()
        if not self.project_id:
            raise ValueError("project_id is required")

    def to_dict(self) -> dict:
        d = super().to_dict()
        d.update(
            {"project_id": self.project_id, "column_name": self.column_name, "workflow_stage": self.workflow_stage}
        )
        return d

    @classmethod
    def from_dict(cls, data: dict) -> "ProjectWorkflowMappingAddedEvent":
        return cls(
            type=data.get("type", "ProjectWorkflowMappingAddedEvent"),
            timestamp=data.get("timestamp", ""),
            source=data.get("source", ""),
            correlation_id=data.get("correlation_id", ""),
            event_id=data.get("event_id", ""),
            project_id=data.get("project_id", ""),
            column_name=data.get("column_name", ""),
            workflow_stage=data.get("workflow_stage", ""),
        )
