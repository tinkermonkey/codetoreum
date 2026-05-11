"""Agent domain events using frozen dataclasses.

All events are immutable frozen dataclasses subclassing CodetoreumEvent.
"""

from dataclasses import dataclass

from .adapter_events import CodetoreumEvent, now_iso


@dataclass(frozen=True)
class AgentCreatedEvent(CodetoreumEvent):
    """Emitted when a new agent is created."""

    agent_id: str = ""
    name: str = ""
    display_name: str = ""
    agent_type: str = ""
    model: str = ""

    def __post_init__(self) -> None:
        super().__post_init__()
        if not self.agent_id:
            raise ValueError("agent_id is required")
        if not self.name:
            raise ValueError("name is required")

    def to_dict(self) -> dict:
        d = super().to_dict()
        d.update(
            {
                "agent_id": self.agent_id,
                "name": self.name,
                "display_name": self.display_name,
                "agent_type": self.agent_type,
                "model": self.model,
            }
        )
        return d

    @classmethod
    def from_dict(cls, data: dict) -> "AgentCreatedEvent":
        return cls(
            type=data.get("type", "agent.created"),
            timestamp=data.get("timestamp", now_iso()),
            source=data.get("source", "domain"),
            correlation_id=data.get("correlation_id"),
            event_id=data.get("event_id", ""),
            agent_id=data.get("agent_id", ""),
            name=data.get("name", ""),
            display_name=data.get("display_name", ""),
            agent_type=data.get("agent_type", ""),
            model=data.get("model", ""),
        )


@dataclass(frozen=True)
class AgentCapabilityAddedEvent(CodetoreumEvent):
    """Emitted when a capability is added to an agent."""

    agent_id: str = ""
    skill: str = ""
    proficiency: float = 0.0

    def __post_init__(self) -> None:
        super().__post_init__()
        if not self.agent_id:
            raise ValueError("agent_id is required")

    def to_dict(self) -> dict:
        d = super().to_dict()
        d.update({"agent_id": self.agent_id, "skill": self.skill, "proficiency": self.proficiency})
        return d

    @classmethod
    def from_dict(cls, data: dict) -> "AgentCapabilityAddedEvent":
        return cls(
            type=data.get("type", "agent.capability_added"),
            timestamp=data.get("timestamp", now_iso()),
            source=data.get("source", "domain"),
            correlation_id=data.get("correlation_id"),
            event_id=data.get("event_id", ""),
            agent_id=data.get("agent_id", ""),
            skill=data.get("skill", ""),
            proficiency=data.get("proficiency", 0.0),
        )


@dataclass(frozen=True)
class AgentCapabilityRemovedEvent(CodetoreumEvent):
    """Emitted when a capability is removed from an agent."""

    agent_id: str = ""
    skill: str = ""

    def __post_init__(self) -> None:
        super().__post_init__()
        if not self.agent_id:
            raise ValueError("agent_id is required")

    def to_dict(self) -> dict:
        d = super().to_dict()
        d.update({"agent_id": self.agent_id, "skill": self.skill})
        return d

    @classmethod
    def from_dict(cls, data: dict) -> "AgentCapabilityRemovedEvent":
        return cls(
            type=data.get("type", "agent.capability_removed"),
            timestamp=data.get("timestamp", now_iso()),
            source=data.get("source", "domain"),
            correlation_id=data.get("correlation_id"),
            event_id=data.get("event_id", ""),
            agent_id=data.get("agent_id", ""),
            skill=data.get("skill", ""),
        )


@dataclass(frozen=True)
class AgentCapabilityUpdatedEvent(CodetoreumEvent):
    """Emitted when a capability proficiency is updated on an agent."""

    agent_id: str = ""
    skill: str = ""
    old_proficiency: float = 0.0
    new_proficiency: float = 0.0

    def __post_init__(self) -> None:
        super().__post_init__()
        if not self.agent_id:
            raise ValueError("agent_id is required")

    def to_dict(self) -> dict:
        d = super().to_dict()
        d.update(
            {
                "agent_id": self.agent_id,
                "skill": self.skill,
                "old_proficiency": self.old_proficiency,
                "new_proficiency": self.new_proficiency,
            }
        )
        return d

    @classmethod
    def from_dict(cls, data: dict) -> "AgentCapabilityUpdatedEvent":
        return cls(
            type=data.get("type", "agent.capability_updated"),
            timestamp=data.get("timestamp", now_iso()),
            source=data.get("source", "domain"),
            correlation_id=data.get("correlation_id"),
            event_id=data.get("event_id", ""),
            agent_id=data.get("agent_id", ""),
            skill=data.get("skill", ""),
            old_proficiency=data.get("old_proficiency", 0.0),
            new_proficiency=data.get("new_proficiency", 0.0),
        )


@dataclass(frozen=True)
class AgentModelUpdatedEvent(CodetoreumEvent):
    """Emitted when an agent's model is updated."""

    agent_id: str = ""
    old_model: str = ""
    new_model: str = ""

    def __post_init__(self) -> None:
        super().__post_init__()
        if not self.agent_id:
            raise ValueError("agent_id is required")

    def to_dict(self) -> dict:
        d = super().to_dict()
        d.update({"agent_id": self.agent_id, "old_model": self.old_model, "new_model": self.new_model})
        return d

    @classmethod
    def from_dict(cls, data: dict) -> "AgentModelUpdatedEvent":
        return cls(
            type=data.get("type", "agent.model_updated"),
            timestamp=data.get("timestamp", now_iso()),
            source=data.get("source", "domain"),
            correlation_id=data.get("correlation_id"),
            event_id=data.get("event_id", ""),
            agent_id=data.get("agent_id", ""),
            old_model=data.get("old_model", ""),
            new_model=data.get("new_model", ""),
        )


@dataclass(frozen=True)
class AgentTimeoutUpdatedEvent(CodetoreumEvent):
    """Emitted when an agent's timeout is updated."""

    agent_id: str = ""
    old_timeout: int = 0
    new_timeout: int = 0

    def __post_init__(self) -> None:
        super().__post_init__()
        if not self.agent_id:
            raise ValueError("agent_id is required")

    def to_dict(self) -> dict:
        d = super().to_dict()
        d.update({"agent_id": self.agent_id, "old_timeout": self.old_timeout, "new_timeout": self.new_timeout})
        return d

    @classmethod
    def from_dict(cls, data: dict) -> "AgentTimeoutUpdatedEvent":
        return cls(
            type=data.get("type", "agent.timeout_updated"),
            timestamp=data.get("timestamp", now_iso()),
            source=data.get("source", "domain"),
            correlation_id=data.get("correlation_id"),
            event_id=data.get("event_id", ""),
            agent_id=data.get("agent_id", ""),
            old_timeout=data.get("old_timeout", 0),
            new_timeout=data.get("new_timeout", 0),
        )


@dataclass(frozen=True)
class AgentMaxRetriesUpdatedEvent(CodetoreumEvent):
    """Emitted when an agent's max retries is updated."""

    agent_id: str = ""
    old_max_retries: int = 0
    new_max_retries: int = 0

    def __post_init__(self) -> None:
        super().__post_init__()
        if not self.agent_id:
            raise ValueError("agent_id is required")

    def to_dict(self) -> dict:
        d = super().to_dict()
        d.update(
            {
                "agent_id": self.agent_id,
                "old_max_retries": self.old_max_retries,
                "new_max_retries": self.new_max_retries,
            }
        )
        return d

    @classmethod
    def from_dict(cls, data: dict) -> "AgentMaxRetriesUpdatedEvent":
        return cls(
            type=data.get("type", "agent.max_retries_updated"),
            timestamp=data.get("timestamp", now_iso()),
            source=data.get("source", "domain"),
            correlation_id=data.get("correlation_id"),
            event_id=data.get("event_id", ""),
            agent_id=data.get("agent_id", ""),
            old_max_retries=data.get("old_max_retries", 0),
            new_max_retries=data.get("new_max_retries", 0),
        )


@dataclass(frozen=True)
class AgentConstraintsUpdatedEvent(CodetoreumEvent):
    """Emitted when an agent's constraints are updated."""

    agent_id: str = ""
    old_constraints: tuple = ()
    new_constraints: tuple = ()

    def __post_init__(self) -> None:
        super().__post_init__()
        if not self.agent_id:
            raise ValueError("agent_id is required")
        object.__setattr__(self, "old_constraints", tuple(self.old_constraints))
        object.__setattr__(self, "new_constraints", tuple(self.new_constraints))

    def to_dict(self) -> dict:
        d = super().to_dict()
        d.update(
            {
                "agent_id": self.agent_id,
                "old_constraints": list(self.old_constraints),
                "new_constraints": list(self.new_constraints),
            }
        )
        return d

    @classmethod
    def from_dict(cls, data: dict) -> "AgentConstraintsUpdatedEvent":
        return cls(
            type=data.get("type", "agent.constraints_updated"),
            timestamp=data.get("timestamp", now_iso()),
            source=data.get("source", "domain"),
            correlation_id=data.get("correlation_id"),
            event_id=data.get("event_id", ""),
            agent_id=data.get("agent_id", ""),
            old_constraints=tuple(data.get("old_constraints", [])),
            new_constraints=tuple(data.get("new_constraints", [])),
        )


@dataclass(frozen=True)
class AgentMcpServerAddedEvent(CodetoreumEvent):
    """Emitted when an MCP server is added to an agent."""

    agent_id: str = ""
    server_name: str = ""

    def __post_init__(self) -> None:
        super().__post_init__()
        if not self.agent_id:
            raise ValueError("agent_id is required")

    def to_dict(self) -> dict:
        d = super().to_dict()
        d.update({"agent_id": self.agent_id, "server_name": self.server_name})
        return d

    @classmethod
    def from_dict(cls, data: dict) -> "AgentMcpServerAddedEvent":
        return cls(
            type=data.get("type", "agent.mcp_server_added"),
            timestamp=data.get("timestamp", now_iso()),
            source=data.get("source", "domain"),
            correlation_id=data.get("correlation_id"),
            event_id=data.get("event_id", ""),
            agent_id=data.get("agent_id", ""),
            server_name=data.get("server_name", ""),
        )


@dataclass(frozen=True)
class AgentMcpServerRemovedEvent(CodetoreumEvent):
    """Emitted when an MCP server is removed from an agent."""

    agent_id: str = ""
    server_name: str = ""

    def __post_init__(self) -> None:
        super().__post_init__()
        if not self.agent_id:
            raise ValueError("agent_id is required")

    def to_dict(self) -> dict:
        d = super().to_dict()
        d.update({"agent_id": self.agent_id, "server_name": self.server_name})
        return d

    @classmethod
    def from_dict(cls, data: dict) -> "AgentMcpServerRemovedEvent":
        return cls(
            type=data.get("type", "agent.mcp_server_removed"),
            timestamp=data.get("timestamp", now_iso()),
            source=data.get("source", "domain"),
            correlation_id=data.get("correlation_id"),
            event_id=data.get("event_id", ""),
            agent_id=data.get("agent_id", ""),
            server_name=data.get("server_name", ""),
        )
