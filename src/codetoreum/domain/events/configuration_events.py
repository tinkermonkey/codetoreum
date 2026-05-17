"""Configuration domain events using frozen dataclasses."""

from dataclasses import dataclass
from typing import Any

from .adapter_events import CodetoreumEvent


@dataclass(frozen=True)
class ProjectConfigUpdatedEvent(CodetoreumEvent):
    """Emitted when project configuration is updated."""

    project_id: str = ""
    config_key: str = ""
    old_value: str = ""
    new_value: str = ""

    def __post_init__(self) -> None:
        super().__post_init__()
        if not self.project_id:
            raise ValueError("project_id is required")

    def to_dict(self) -> dict[str, Any]:
        d = super().to_dict()
        d.update(
            {
                "project_id": self.project_id,
                "config_key": self.config_key,
                "old_value": self.old_value,
                "new_value": self.new_value,
            }
        )
        return d

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ProjectConfigUpdatedEvent":
        return cls(
            type=data.get("type", "ProjectConfigUpdatedEvent"),
            timestamp=data.get("timestamp", ""),
            source=data.get("source", ""),
            correlation_id=data.get("correlation_id", ""),
            event_id=data.get("event_id", ""),
            project_id=data.get("project_id", ""),
            config_key=data.get("config_key", ""),
            old_value=data.get("old_value", ""),
            new_value=data.get("new_value", ""),
        )


@dataclass(frozen=True)
class AgentConfigUpdatedEvent(CodetoreumEvent):
    """Emitted when agent configuration is updated."""

    agent_id: str = ""
    config_key: str = ""
    old_value: str = ""
    new_value: str = ""

    def __post_init__(self) -> None:
        super().__post_init__()
        if not self.agent_id:
            raise ValueError("agent_id is required")

    def to_dict(self) -> dict[str, Any]:
        d = super().to_dict()
        d.update(
            {
                "agent_id": self.agent_id,
                "config_key": self.config_key,
                "old_value": self.old_value,
                "new_value": self.new_value,
            }
        )
        return d

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "AgentConfigUpdatedEvent":
        return cls(
            type=data.get("type", "AgentConfigUpdatedEvent"),
            timestamp=data.get("timestamp", ""),
            source=data.get("source", ""),
            correlation_id=data.get("correlation_id", ""),
            event_id=data.get("event_id", ""),
            agent_id=data.get("agent_id", ""),
            config_key=data.get("config_key", ""),
            old_value=data.get("old_value", ""),
            new_value=data.get("new_value", ""),
        )


@dataclass(frozen=True)
class PipelineConfigUpdatedEvent(CodetoreumEvent):
    """Emitted when pipeline configuration is updated."""

    pipeline_id: str = ""
    config_key: str = ""
    old_value: str = ""
    new_value: str = ""

    def __post_init__(self) -> None:
        super().__post_init__()

    def to_dict(self) -> dict[str, Any]:
        d = super().to_dict()
        d.update(
            {
                "pipeline_id": self.pipeline_id,
                "config_key": self.config_key,
                "old_value": self.old_value,
                "new_value": self.new_value,
            }
        )
        return d

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "PipelineConfigUpdatedEvent":
        return cls(
            type=data.get("type", "PipelineConfigUpdatedEvent"),
            timestamp=data.get("timestamp", ""),
            source=data.get("source", ""),
            correlation_id=data.get("correlation_id", ""),
            event_id=data.get("event_id", ""),
            pipeline_id=data.get("pipeline_id", ""),
            config_key=data.get("config_key", ""),
            old_value=data.get("old_value", ""),
            new_value=data.get("new_value", ""),
        )


@dataclass(frozen=True)
class EnvironmentVariableChangedEvent(CodetoreumEvent):
    """Emitted when an environment variable is changed."""

    project_id: str = ""
    variable_name: str = ""
    old_value: str = ""
    new_value: str = ""

    def __post_init__(self) -> None:
        super().__post_init__()

    def to_dict(self) -> dict[str, Any]:
        d = super().to_dict()
        d.update(
            {
                "project_id": self.project_id,
                "variable_name": self.variable_name,
                "old_value": self.old_value,
                "new_value": self.new_value,
            }
        )
        return d

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "EnvironmentVariableChangedEvent":
        return cls(
            type=data.get("type", "EnvironmentVariableChangedEvent"),
            timestamp=data.get("timestamp", ""),
            source=data.get("source", ""),
            correlation_id=data.get("correlation_id", ""),
            event_id=data.get("event_id", ""),
            project_id=data.get("project_id", ""),
            variable_name=data.get("variable_name", ""),
            old_value=data.get("old_value", ""),
            new_value=data.get("new_value", ""),
        )


@dataclass(frozen=True)
class CommandMountedEvent(CodetoreumEvent):
    """Emitted when a command is mounted."""

    project_id: str = ""
    command_name: str = ""

    def __post_init__(self) -> None:
        super().__post_init__()

    def to_dict(self) -> dict[str, Any]:
        d = super().to_dict()
        d.update({"project_id": self.project_id, "command_name": self.command_name})
        return d

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "CommandMountedEvent":
        return cls(
            type=data.get("type", "CommandMountedEvent"),
            timestamp=data.get("timestamp", ""),
            source=data.get("source", ""),
            correlation_id=data.get("correlation_id", ""),
            event_id=data.get("event_id", ""),
            project_id=data.get("project_id", ""),
            command_name=data.get("command_name", ""),
        )


@dataclass(frozen=True)
class CommandUnmountedEvent(CodetoreumEvent):
    """Emitted when a command is unmounted."""

    project_id: str = ""
    command_name: str = ""

    def __post_init__(self) -> None:
        super().__post_init__()

    def to_dict(self) -> dict[str, Any]:
        d = super().to_dict()
        d.update({"project_id": self.project_id, "command_name": self.command_name})
        return d

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "CommandUnmountedEvent":
        return cls(
            type=data.get("type", "CommandUnmountedEvent"),
            timestamp=data.get("timestamp", ""),
            source=data.get("source", ""),
            correlation_id=data.get("correlation_id", ""),
            event_id=data.get("event_id", ""),
            project_id=data.get("project_id", ""),
            command_name=data.get("command_name", ""),
        )


@dataclass(frozen=True)
class SubAgentMountedEvent(CodetoreumEvent):
    """Emitted when a sub-agent is mounted."""

    project_id: str = ""
    agent_id: str = ""

    def __post_init__(self) -> None:
        super().__post_init__()

    def to_dict(self) -> dict[str, Any]:
        d = super().to_dict()
        d.update({"project_id": self.project_id, "agent_id": self.agent_id})
        return d

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "SubAgentMountedEvent":
        return cls(
            type=data.get("type", "SubAgentMountedEvent"),
            timestamp=data.get("timestamp", ""),
            source=data.get("source", ""),
            correlation_id=data.get("correlation_id", ""),
            event_id=data.get("event_id", ""),
            project_id=data.get("project_id", ""),
            agent_id=data.get("agent_id", ""),
        )


@dataclass(frozen=True)
class SubAgentUnmountedEvent(CodetoreumEvent):
    """Emitted when a sub-agent is unmounted."""

    project_id: str = ""
    agent_id: str = ""

    def __post_init__(self) -> None:
        super().__post_init__()

    def to_dict(self) -> dict[str, Any]:
        d = super().to_dict()
        d.update({"project_id": self.project_id, "agent_id": self.agent_id})
        return d

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "SubAgentUnmountedEvent":
        return cls(
            type=data.get("type", "SubAgentUnmountedEvent"),
            timestamp=data.get("timestamp", ""),
            source=data.get("source", ""),
            correlation_id=data.get("correlation_id", ""),
            event_id=data.get("event_id", ""),
            project_id=data.get("project_id", ""),
            agent_id=data.get("agent_id", ""),
        )
