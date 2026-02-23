"""Agent entity and value objects."""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional
from uuid import uuid4

from codetoreum.domain.events import (
    AgentCapabilityAdded,
    AgentCapabilityRemoved,
    AgentCapabilityUpdated,
    AgentConstraintsUpdated,
    AgentCreated,
    AgentMaxRetriesUpdated,
    AgentMcpServerAdded,
    AgentMcpServerRemoved,
    AgentModelUpdated,
    AgentTimeoutUpdated,
    DomainEvent,
)
from codetoreum.domain.exceptions import DomainError


class AgentType(Enum):
    """Types of agents in the system."""

    # Generic workflow roles
    MAKER = "maker"  # Creates/produces output
    REVIEWER = "reviewer"  # Reviews output
    SPECIALIZED = "specialized"  # Specific task (e.g., dev env setup)

    # Specific agent types (as per requirements)
    REQUIREMENTS_ANALYST = "requirements_analyst"
    ARCHITECT = "architect"
    DEVELOPER = "developer"
    TESTER = "tester"
    DEVOPS = "devops"


@dataclass
class AgentCapability:
    """Represents a skill/capability of an agent."""

    skill: str
    proficiency: float  # 0.0 to 1.0
    description: Optional[str] = None

    def __post_init__(self) -> None:
        """Validate proficiency range."""
        if not 0.0 <= self.proficiency <= 1.0:
            raise DomainError("Proficiency must be between 0.0 and 1.0")


@dataclass
class Agent:
    """
    Agent aggregate root.

    Represents an AI agent with capabilities, configuration, and constraints.
    """

    # Identity
    id: str
    name: str
    display_name: str
    agent_type: AgentType

    # Capabilities
    capabilities: Dict[str, AgentCapability]
    role_description: str

    # Configuration
    model: str  # LLM model (e.g., "claude-sonnet-4-5")
    timeout_seconds: int
    max_retries: int

    # Constraints
    requires_docker: bool
    requires_dev_container: bool
    makes_code_changes: bool
    filesystem_write_allowed: bool

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

    def __post_init__(self) -> None:
        """Validate invariants after initialization."""
        self._validate_invariants()

    def _validate_invariants(self) -> None:
        """
        Validate domain invariants.

        Invariants:
        - Must have a non-empty name
        - Must have at least one capability
        - Timeout must be positive
        - Max retries must be non-negative
        - Model must be specified
        """
        if not self.name or not self.name.strip():
            raise DomainError("Agent must have a non-empty name")

        if not self.capabilities:
            raise DomainError("Agent must have at least one capability")

        if self.timeout_seconds <= 0:
            raise DomainError("Timeout must be positive")

        if self.max_retries < 0:
            raise DomainError("Max retries must be non-negative")

        if not self.model:
            raise DomainError("Agent must specify a model")

    @classmethod
    def create(
        cls,
        name: str,
        display_name: str,
        agent_type: AgentType,
        role_description: str,
        model: str,
        capabilities: Dict[str, AgentCapability],
        timeout_seconds: int = 300,
        max_retries: int = 3,
        requires_docker: bool = True,
        requires_dev_container: bool = False,
        makes_code_changes: bool = False,
        filesystem_write_allowed: bool = True,
        mcp_servers: Optional[List[str]] = None,
    ) -> "Agent":
        """
        Factory method to create a new agent.

        Args:
            name: Agent name (identifier)
            display_name: Human-readable agent name
            agent_type: Type of agent (maker, reviewer, specialized)
            role_description: Description of agent's role
            model: LLM model to use
            capabilities: Dictionary of agent capabilities
            timeout_seconds: Execution timeout (default: 300)
            max_retries: Maximum retry attempts (default: 3)
            requires_docker: Whether agent requires Docker (default: True)
            requires_dev_container: Whether agent requires dev container (default: False)
            makes_code_changes: Whether agent makes code changes (default: False)
            filesystem_write_allowed: Whether agent can write files (default: True)
            mcp_servers: Optional list of MCP server names

        Returns:
            Newly created Agent instance

        Emits: AgentCreated event
        """
        agent = cls(
            id=str(uuid4()),
            name=name,
            display_name=display_name,
            agent_type=agent_type,
            capabilities=capabilities,
            role_description=role_description,
            model=model,
            timeout_seconds=timeout_seconds,
            max_retries=max_retries,
            requires_docker=requires_docker,
            requires_dev_container=requires_dev_container,
            makes_code_changes=makes_code_changes,
            filesystem_write_allowed=filesystem_write_allowed,
            mcp_servers=mcp_servers or [],
            metadata={},
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )

        event = AgentCreated(
            aggregate_id=agent.id,
            payload={
                "name": name,
                "display_name": display_name,
                "agent_type": agent_type.value,
                "model": model,
                "capabilities": [c.skill for c in capabilities.values()],
            },
        )
        agent._add_event(event)

        return agent

    # Capability management
    def add_capability(self, capability: AgentCapability) -> None:
        """
        Add a new capability to the agent.

        Args:
            capability: AgentCapability to add

        Raises:
            DomainError: If agent already has this capability

        Emits: AgentCapabilityAdded event
        """
        if capability.skill in self.capabilities:
            raise DomainError(f"Agent already has capability {capability.skill}")

        self.capabilities[capability.skill] = capability
        self.updated_at = datetime.now(timezone.utc)
        self._version += 1

        event = AgentCapabilityAdded(
            aggregate_id=self.id,
            payload={
                "skill": capability.skill,
                "proficiency": capability.proficiency,
                "added_at": self.updated_at.isoformat(),
            },
        )
        self._add_event(event)

    def remove_capability(self, skill: str) -> None:
        """
        Remove a capability from the agent.

        Business rules:
        - Cannot remove last capability

        Args:
            skill: Skill name to remove

        Raises:
            DomainError: If agent doesn't have capability or it's the last one

        Emits: AgentCapabilityRemoved event
        """
        if skill not in self.capabilities:
            raise DomainError(f"Agent does not have capability {skill}")

        if len(self.capabilities) == 1:
            raise DomainError("Cannot remove last capability")

        del self.capabilities[skill]
        self.updated_at = datetime.now(timezone.utc)
        self._version += 1

        event = AgentCapabilityRemoved(
            aggregate_id=self.id,
            payload={"skill": skill, "removed_at": self.updated_at.isoformat()},
        )
        self._add_event(event)

    def update_capability_proficiency(self, skill: str, proficiency: float) -> None:
        """
        Update proficiency level for a capability.

        Args:
            skill: Skill name to update
            proficiency: New proficiency level (0.0 to 1.0)

        Raises:
            DomainError: If agent doesn't have capability or proficiency is invalid

        Emits: AgentCapabilityUpdated event
        """
        if skill not in self.capabilities:
            raise DomainError(f"Agent does not have capability {skill}")

        if not 0.0 <= proficiency <= 1.0:
            raise DomainError("Proficiency must be between 0.0 and 1.0")

        old_proficiency = self.capabilities[skill].proficiency
        self.capabilities[skill].proficiency = proficiency
        self.updated_at = datetime.now(timezone.utc)
        self._version += 1

        event = AgentCapabilityUpdated(
            aggregate_id=self.id,
            payload={
                "skill": skill,
                "old_proficiency": old_proficiency,
                "new_proficiency": proficiency,
                "updated_at": self.updated_at.isoformat(),
            },
        )
        self._add_event(event)

    # Configuration management
    def update_model(self, model: str) -> None:
        """
        Update the LLM model used by this agent.

        Args:
            model: New model name

        Raises:
            DomainError: If model is empty

        Emits: AgentModelUpdated event
        """
        if not model:
            raise DomainError("Model cannot be empty")

        old_model = self.model
        self.model = model
        self.updated_at = datetime.now(timezone.utc)
        self._version += 1

        event = AgentModelUpdated(
            aggregate_id=self.id,
            payload={
                "old_model": old_model,
                "new_model": model,
                "updated_at": self.updated_at.isoformat(),
            },
        )
        self._add_event(event)

    def update_timeout(self, timeout_seconds: int) -> None:
        """
        Update agent timeout.

        Args:
            timeout_seconds: New timeout in seconds

        Raises:
            DomainError: If timeout is not positive

        Emits: AgentTimeoutUpdated event
        """
        if timeout_seconds <= 0:
            raise DomainError("Timeout must be positive")

        old_timeout = self.timeout_seconds
        self.timeout_seconds = timeout_seconds
        self.updated_at = datetime.now(timezone.utc)
        self._version += 1

        event = AgentTimeoutUpdated(
            aggregate_id=self.id,
            payload={
                "old_timeout": old_timeout,
                "new_timeout": timeout_seconds,
                "updated_at": self.updated_at.isoformat(),
            },
        )
        self._add_event(event)

    def update_max_retries(self, max_retries: int) -> None:
        """
        Update agent max retries.

        Args:
            max_retries: New max retries value

        Raises:
            DomainError: If max_retries is negative

        Emits: AgentMaxRetriesUpdated event
        """
        if max_retries < 0:
            raise DomainError("Max retries must be non-negative")

        old_max_retries = self.max_retries
        self.max_retries = max_retries
        self.updated_at = datetime.now(timezone.utc)
        self._version += 1

        event = AgentMaxRetriesUpdated(
            aggregate_id=self.id,
            payload={
                "old_max_retries": old_max_retries,
                "new_max_retries": max_retries,
                "updated_at": self.updated_at.isoformat(),
            },
        )
        self._add_event(event)

    def update_constraints(
        self,
        requires_docker: Optional[bool] = None,
        requires_dev_container: Optional[bool] = None,
        makes_code_changes: Optional[bool] = None,
        filesystem_write_allowed: Optional[bool] = None,
    ) -> None:
        """
        Update agent constraints.

        Args:
            requires_docker: Whether agent requires Docker
            requires_dev_container: Whether agent requires dev container
            makes_code_changes: Whether agent makes code changes
            filesystem_write_allowed: Whether agent can write files

        Raises:
            DomainError: If any non-None value is not a boolean

        Emits: AgentConstraintsUpdated event
        """
        # Validate types
        if requires_docker is not None and not isinstance(requires_docker, bool):
            raise DomainError("requires_docker must be a boolean")
        if requires_dev_container is not None and not isinstance(requires_dev_container, bool):
            raise DomainError("requires_dev_container must be a boolean")
        if makes_code_changes is not None and not isinstance(makes_code_changes, bool):
            raise DomainError("makes_code_changes must be a boolean")
        if filesystem_write_allowed is not None and not isinstance(filesystem_write_allowed, bool):
            raise DomainError("filesystem_write_allowed must be a boolean")

        old_constraints = {
            "requires_docker": self.requires_docker,
            "requires_dev_container": self.requires_dev_container,
            "makes_code_changes": self.makes_code_changes,
            "filesystem_write_allowed": self.filesystem_write_allowed,
        }

        if requires_docker is not None:
            self.requires_docker = requires_docker
        if requires_dev_container is not None:
            self.requires_dev_container = requires_dev_container
        if makes_code_changes is not None:
            self.makes_code_changes = makes_code_changes
        if filesystem_write_allowed is not None:
            self.filesystem_write_allowed = filesystem_write_allowed

        self.updated_at = datetime.now(timezone.utc)
        self._version += 1

        event = AgentConstraintsUpdated(
            aggregate_id=self.id,
            payload={
                "old_constraints": old_constraints,
                "new_constraints": {
                    "requires_docker": self.requires_docker,
                    "requires_dev_container": self.requires_dev_container,
                    "makes_code_changes": self.makes_code_changes,
                    "filesystem_write_allowed": self.filesystem_write_allowed,
                },
                "updated_at": self.updated_at.isoformat(),
            },
        )
        self._add_event(event)

    # MCP server management
    def add_mcp_server(self, server_name: str) -> None:
        """
        Add an MCP server to agent configuration.

        Args:
            server_name: Name of MCP server to add

        Raises:
            DomainError: If server is already configured

        Emits: AgentMcpServerAdded event
        """
        if server_name in self.mcp_servers:
            raise DomainError(f"MCP server {server_name} already configured")

        self.mcp_servers.append(server_name)
        self.updated_at = datetime.now(timezone.utc)
        self._version += 1

        event = AgentMcpServerAdded(
            aggregate_id=self.id,
            payload={
                "server_name": server_name,
                "added_at": self.updated_at.isoformat(),
            },
        )
        self._add_event(event)

    def remove_mcp_server(self, server_name: str) -> None:
        """
        Remove an MCP server from agent configuration.

        Args:
            server_name: Name of MCP server to remove

        Raises:
            DomainError: If server is not configured

        Emits: AgentMcpServerRemoved event
        """
        if server_name not in self.mcp_servers:
            raise DomainError(f"MCP server {server_name} not configured")

        self.mcp_servers.remove(server_name)
        self.updated_at = datetime.now(timezone.utc)
        self._version += 1

        event = AgentMcpServerRemoved(
            aggregate_id=self.id,
            payload={
                "server_name": server_name,
                "removed_at": self.updated_at.isoformat(),
            },
        )
        self._add_event(event)

    # Query methods
    def has_capability(self, skill: str, min_proficiency: float = 0.0) -> bool:
        """
        Check if agent has a capability with minimum proficiency.

        Args:
            skill: Skill name to check
            min_proficiency: Minimum proficiency level (default: 0.0)

        Returns:
            True if agent has capability with sufficient proficiency
        """
        if skill not in self.capabilities:
            return False
        return self.capabilities[skill].proficiency >= min_proficiency

    def get_capability_score(self, skill: str) -> float:
        """
        Get proficiency score for a capability (0.0 if not present).

        Args:
            skill: Skill name to query

        Returns:
            Proficiency score (0.0 to 1.0)
        """
        if skill not in self.capabilities:
            return 0.0
        return self.capabilities[skill].proficiency

    def can_execute_in_environment(
        self, has_docker: bool, has_dev_container: bool
    ) -> bool:
        """
        Check if agent can execute in given environment.

        Args:
            has_docker: Whether Docker is available
            has_dev_container: Whether dev container is available

        Returns:
            True if agent can execute in this environment
        """
        if self.requires_docker and not has_docker:
            return False
        if self.requires_dev_container and not has_dev_container:
            return False
        return True

    def is_maker_agent(self) -> bool:
        """
        Check if this is a maker agent.

        Returns:
            True if agent type is MAKER
        """
        return self.agent_type == AgentType.MAKER

    def is_reviewer_agent(self) -> bool:
        """
        Check if this is a reviewer agent.

        Returns:
            True if agent type is REVIEWER
        """
        return self.agent_type == AgentType.REVIEWER

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
            Shallow copy of the pending events list. Creates a new list
            containing references to the same event objects.
        """
        return list(self._events)

    def clear_events(self) -> None:
        """Clear pending events."""
        self._events.clear()
