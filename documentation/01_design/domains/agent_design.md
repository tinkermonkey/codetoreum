# Agent Domain Design

## Overview

The Agent is a core aggregate root representing AI agents with specific capabilities that perform work in the system. It encapsulates agent configuration, capabilities, and constraints.

## Domain Model

### Aggregate Root: Agent

```python
from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any, Set
from datetime import datetime
from enum import Enum
from uuid import UUID, uuid4

class AgentType(Enum):
    """Types of agents in the system."""
    MAKER = "maker"  # Creates/produces output
    REVIEWER = "reviewer"  # Reviews output
    SPECIALIZED = "specialized"  # Specific task (e.g., dev env setup)

@dataclass
class AgentCapability:
    """Represents a skill/capability of an agent."""
    skill: str
    proficiency: float  # 0.0 to 1.0
    description: Optional[str] = None

    def __post_init__(self):
        if not 0.0 <= self.proficiency <= 1.0:
            raise ValueError("Proficiency must be between 0.0 and 1.0")

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

    def __post_init__(self):
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
    def create(cls,
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
               mcp_servers: Optional[List[str]] = None) -> 'Agent':
        """
        Factory method to create a new agent.

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
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow()
        )

        event = AgentCreated(
            aggregate_id=agent.id,
            aggregate_type="Agent",
            payload={
                "name": name,
                "display_name": display_name,
                "agent_type": agent_type.value,
                "model": model,
                "capabilities": [c.skill for c in capabilities.values()]
            }
        )
        agent._add_event(event)

        return agent

    # Capability management
    def add_capability(self, capability: AgentCapability) -> None:
        """
        Add a new capability to the agent.

        Emits: AgentCapabilityAdded event
        """
        if capability.skill in self.capabilities:
            raise DomainError(f"Agent already has capability {capability.skill}")

        self.capabilities[capability.skill] = capability
        self.updated_at = datetime.utcnow()
        self._version += 1

        event = AgentCapabilityAdded(
            aggregate_id=self.id,
            aggregate_type="Agent",
            payload={
                "skill": capability.skill,
                "proficiency": capability.proficiency,
                "added_at": self.updated_at.isoformat()
            }
        )
        self._add_event(event)

    def remove_capability(self, skill: str) -> None:
        """
        Remove a capability from the agent.

        Business rules:
        - Cannot remove last capability

        Emits: AgentCapabilityRemoved event
        """
        if skill not in self.capabilities:
            raise DomainError(f"Agent does not have capability {skill}")

        if len(self.capabilities) == 1:
            raise DomainError("Cannot remove last capability")

        del self.capabilities[skill]
        self.updated_at = datetime.utcnow()
        self._version += 1

        event = AgentCapabilityRemoved(
            aggregate_id=self.id,
            aggregate_type="Agent",
            payload={
                "skill": skill,
                "removed_at": self.updated_at.isoformat()
            }
        )
        self._add_event(event)

    def update_capability_proficiency(self, skill: str, proficiency: float) -> None:
        """
        Update proficiency level for a capability.

        Emits: AgentCapabilityUpdated event
        """
        if skill not in self.capabilities:
            raise DomainError(f"Agent does not have capability {skill}")

        if not 0.0 <= proficiency <= 1.0:
            raise DomainError("Proficiency must be between 0.0 and 1.0")

        old_proficiency = self.capabilities[skill].proficiency
        self.capabilities[skill].proficiency = proficiency
        self.updated_at = datetime.utcnow()
        self._version += 1

        event = AgentCapabilityUpdated(
            aggregate_id=self.id,
            aggregate_type="Agent",
            payload={
                "skill": skill,
                "old_proficiency": old_proficiency,
                "new_proficiency": proficiency,
                "updated_at": self.updated_at.isoformat()
            }
        )
        self._add_event(event)

    # Configuration management
    def update_model(self, model: str) -> None:
        """
        Update the LLM model used by this agent.

        Emits: AgentModelUpdated event
        """
        if not model:
            raise DomainError("Model cannot be empty")

        old_model = self.model
        self.model = model
        self.updated_at = datetime.utcnow()
        self._version += 1

        event = AgentModelUpdated(
            aggregate_id=self.id,
            aggregate_type="Agent",
            payload={
                "old_model": old_model,
                "new_model": model,
                "updated_at": self.updated_at.isoformat()
            }
        )
        self._add_event(event)

    def update_timeout(self, timeout_seconds: int) -> None:
        """
        Update agent timeout.

        Emits: AgentTimeoutUpdated event
        """
        if timeout_seconds <= 0:
            raise DomainError("Timeout must be positive")

        old_timeout = self.timeout_seconds
        self.timeout_seconds = timeout_seconds
        self.updated_at = datetime.utcnow()
        self._version += 1

        event = AgentTimeoutUpdated(
            aggregate_id=self.id,
            aggregate_type="Agent",
            payload={
                "old_timeout": old_timeout,
                "new_timeout": timeout_seconds,
                "updated_at": self.updated_at.isoformat()
            }
        )
        self._add_event(event)

    def update_constraints(self,
                          requires_docker: Optional[bool] = None,
                          requires_dev_container: Optional[bool] = None,
                          makes_code_changes: Optional[bool] = None,
                          filesystem_write_allowed: Optional[bool] = None) -> None:
        """
        Update agent constraints.

        Emits: AgentConstraintsUpdated event
        """
        old_constraints = {
            "requires_docker": self.requires_docker,
            "requires_dev_container": self.requires_dev_container,
            "makes_code_changes": self.makes_code_changes,
            "filesystem_write_allowed": self.filesystem_write_allowed
        }

        if requires_docker is not None:
            self.requires_docker = requires_docker
        if requires_dev_container is not None:
            self.requires_dev_container = requires_dev_container
        if makes_code_changes is not None:
            self.makes_code_changes = makes_code_changes
        if filesystem_write_allowed is not None:
            self.filesystem_write_allowed = filesystem_write_allowed

        self.updated_at = datetime.utcnow()
        self._version += 1

        event = AgentConstraintsUpdated(
            aggregate_id=self.id,
            aggregate_type="Agent",
            payload={
                "old_constraints": old_constraints,
                "new_constraints": {
                    "requires_docker": self.requires_docker,
                    "requires_dev_container": self.requires_dev_container,
                    "makes_code_changes": self.makes_code_changes,
                    "filesystem_write_allowed": self.filesystem_write_allowed
                },
                "updated_at": self.updated_at.isoformat()
            }
        )
        self._add_event(event)

    # MCP server management
    def add_mcp_server(self, server_name: str) -> None:
        """
        Add an MCP server to agent configuration.

        Emits: AgentMcpServerAdded event
        """
        if server_name in self.mcp_servers:
            raise DomainError(f"MCP server {server_name} already configured")

        self.mcp_servers.append(server_name)
        self.updated_at = datetime.utcnow()
        self._version += 1

        event = AgentMcpServerAdded(
            aggregate_id=self.id,
            aggregate_type="Agent",
            payload={
                "server_name": server_name,
                "added_at": self.updated_at.isoformat()
            }
        )
        self._add_event(event)

    def remove_mcp_server(self, server_name: str) -> None:
        """
        Remove an MCP server from agent configuration.

        Emits: AgentMcpServerRemoved event
        """
        if server_name not in self.mcp_servers:
            raise DomainError(f"MCP server {server_name} not configured")

        self.mcp_servers.remove(server_name)
        self.updated_at = datetime.utcnow()
        self._version += 1

        event = AgentMcpServerRemoved(
            aggregate_id=self.id,
            aggregate_type="Agent",
            payload={
                "server_name": server_name,
                "removed_at": self.updated_at.isoformat()
            }
        )
        self._add_event(event)

    # Query methods
    def has_capability(self, skill: str, min_proficiency: float = 0.0) -> bool:
        """Check if agent has a capability with minimum proficiency."""
        if skill not in self.capabilities:
            return False
        return self.capabilities[skill].proficiency >= min_proficiency

    def get_capability_score(self, skill: str) -> float:
        """Get proficiency score for a capability (0.0 if not present)."""
        if skill not in self.capabilities:
            return 0.0
        return self.capabilities[skill].proficiency

    def can_execute_in_environment(self, has_docker: bool, has_dev_container: bool) -> bool:
        """Check if agent can execute in given environment."""
        if self.requires_docker and not has_docker:
            return False
        if self.requires_dev_container and not has_dev_container:
            return False
        return True

    def is_maker_agent(self) -> bool:
        """Check if this is a maker agent."""
        return self.agent_type == AgentType.MAKER

    def is_reviewer_agent(self) -> bool:
        """Check if this is a reviewer agent."""
        return self.agent_type == AgentType.REVIEWER

    # Event management
    def _add_event(self, event: DomainEvent) -> None:
        """Add event to pending events list."""
        self._events.append(event)

    def get_pending_events(self) -> List[DomainEvent]:
        """Get all pending events."""
        return self._events.copy()

    def clear_events(self) -> None:
        """Clear pending events."""
        self._events.clear()
```

## Domain Events

### AgentCreated
Emitted when a new agent is created.

### AgentCapabilityAdded / AgentCapabilityRemoved / AgentCapabilityUpdated
Emitted when agent capabilities change.

### AgentModelUpdated
Emitted when agent's LLM model is changed.

### AgentTimeoutUpdated
Emitted when agent timeout is modified.

### AgentConstraintsUpdated
Emitted when agent constraints are modified.

### AgentMcpServerAdded / AgentMcpServerRemoved
Emitted when MCP server configuration changes.

## Business Rules

### Creation Rules
1. Must have non-empty name
2. Must have at least one capability
3. Must specify LLM model
4. Timeout must be positive
5. Max retries must be non-negative

### Capability Rules
1. Proficiency must be between 0.0 and 1.0
2. Cannot remove last capability
3. Cannot add duplicate capabilities

### Constraint Rules
1. Agents requiring dev container must also require Docker
2. Agents making code changes should have filesystem write allowed

## Domain Services

### AgentMatchingService

```python
class AgentMatchingService:
    """Service for matching agents to requirements."""

    @staticmethod
    def calculate_match_score(agent: Agent,
                             requirements: List['Requirement']) -> float:
        """
        Calculate match score between agent and requirements.

        Returns score from 0.0 (no match) to 1.0 (perfect match).
        """
        if not requirements:
            return 1.0

        scores = []
        for requirement in requirements:
            if agent.has_capability(requirement.skill):
                capability_score = agent.get_capability_score(requirement.skill)
                requirement_score = min(
                    capability_score / requirement.min_proficiency,
                    1.0
                )
                scores.append(requirement_score)
            else:
                scores.append(0.0)

        return sum(scores) / len(scores) if scores else 0.0

    @staticmethod
    def find_best_match(agents: List[Agent],
                       requirements: List['Requirement']) -> Optional[Agent]:
        """Find agent with highest match score."""
        if not agents:
            return None

        best_agent = None
        best_score = 0.0

        for agent in agents:
            score = AgentMatchingService.calculate_match_score(agent, requirements)
            if score > best_score:
                best_score = score
                best_agent = agent

        return best_agent if best_score > 0.0 else None
```

## Integration Points

### Input Ports
- **ConfigCommandPort**: Configure agents

### Output Ports
- **ILLMProvider**: Execute agent with configured model
- **IContainer**: Run agent in Docker container if required

## CQRS Read Model

```python
@dataclass
class AgentReadModel:
    """Optimized read model for agent queries."""
    id: str
    name: str
    display_name: str
    agent_type: str
    capabilities: List[str]
    model: str
    timeout_seconds: int
    requires_docker: bool
    requires_dev_container: bool
    makes_code_changes: bool
    created_at: datetime
    updated_at: datetime

    # Denormalized metrics
    total_executions: int
    successful_executions: int
    average_duration_seconds: float
    success_rate: float
```

## Testing Approach

```python
def test_create_agent():
    """Test agent creation."""
    capabilities = {
        "python": AgentCapability("python", 0.9),
        "testing": AgentCapability("testing", 0.8)
    }

    agent = Agent.create(
        name="senior_engineer",
        display_name="Senior Software Engineer",
        agent_type=AgentType.MAKER,
        role_description="Implements features",
        model="claude-sonnet-4-5",
        capabilities=capabilities
    )

    assert agent.id is not None
    assert len(agent.capabilities) == 2
    assert agent.has_capability("python", 0.8)

def test_agent_matching():
    """Test agent matching service."""
    agent = create_test_agent_with_python()
    requirements = [
        Requirement("python", min_proficiency=0.7),
        Requirement("testing", min_proficiency=0.6)
    ]

    score = AgentMatchingService.calculate_match_score(agent, requirements)

    assert score > 0.9  # Good match

def test_cannot_remove_last_capability():
    """Test invariant: must have at least one capability."""
    agent = create_test_agent_single_capability()

    with pytest.raises(DomainError):
        agent.remove_capability("python")
```

## Migration from Legacy

### Legacy Mapping
| Legacy | Domain | Notes |
|--------|--------|-------|
| agent_config dict | Agent aggregate | Structured entity |
| agent_name | agent.name | Same |
| model | agent.model | Explicit field |
| timeout | agent.timeout_seconds | Type-safe |
| requires_docker | agent.requires_docker | First-class constraint |

### Key Improvements
1. **Capability System**: Structured skills with proficiency
2. **Type Safety**: Enums for agent types
3. **Constraint Validation**: Built-in constraint checking
4. **Event Sourcing**: Track all configuration changes
5. **Domain Services**: Agent matching logic

## References

- **Agent Execution**: `agent_execution_design.md`
- **Domain Services**: `domain_services_design.md`
- **Value Objects**: `value_objects_design.md`
