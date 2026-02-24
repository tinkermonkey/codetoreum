"""
Mock Agent Command Adapter

In-memory implementation of IAgentCommandPort for development and testing.
"""

from datetime import datetime, timezone
from threading import RLock
from uuid import uuid4

from codetoreum.domain.agent import Agent, AgentCapability
from codetoreum.domain.exceptions import AgentNotFoundError, DomainError
from codetoreum.ports.input.agent_command import (
    AddAgentCapabilityCommand,
    AddMcpServerCommand,
    AgentCommandResult,
    CreateAgentCommand,
    IAgentCommandPort,
    RemoveAgentCapabilityCommand,
    RemoveMcpServerCommand,
    UpdateAgentCapabilityCommand,
    UpdateAgentCommand,
)


class MockAgentCommandAdapter(IAgentCommandPort):
    """
    Mock implementation of IAgentCommandPort using in-memory storage.

    This adapter stores agents in a dictionary and provides full command capabilities
    without requiring a database or event store. It's thread-safe and suitable for
    testing and development environments.
    """

    def __init__(self):
        self._agents: dict[str, Agent] = {}
        self._agents_by_name: dict[str, str] = {}  # name -> agent_id
        self._lock = RLock()

    async def create_agent(self, command: CreateAgentCommand) -> Agent:
        """Create a new agent."""
        with self._lock:
            # Check if agent with same name exists
            if command.name in self._agents_by_name:
                raise DomainError(f"Agent with name '{command.name}' already exists")

            # Create agent
            agent_id = str(uuid4())
            now = datetime.now(timezone.utc)

            agent = Agent(
                id=agent_id,
                name=command.name,
                display_name=command.display_name,
                agent_type=command.agent_type,
                capabilities=command.capabilities.copy(),
                role_description=command.role_description,
                model=command.model,
                timeout_seconds=command.timeout_seconds,
                max_retries=command.max_retries,
                requires_docker=command.requires_docker,
                requires_dev_container=command.requires_dev_container,
                makes_code_changes=command.makes_code_changes,
                filesystem_write_allowed=command.filesystem_write_allowed,
                mcp_servers=command.mcp_servers.copy() if command.mcp_servers else [],
                metadata={},
                created_at=now,
                updated_at=now,
            )

            # Store agent
            self._agents[agent_id] = agent
            self._agents_by_name[command.name] = agent_id

            return agent

    async def update_agent(self, command: UpdateAgentCommand) -> Agent:
        """Update an existing agent."""
        with self._lock:
            if command.agent_id not in self._agents:
                raise AgentNotFoundError(command.agent_id)

            agent = self._agents[command.agent_id]

            # Update fields
            if command.display_name is not None:
                agent.display_name = command.display_name

            if command.role_description is not None:
                agent.role_description = command.role_description

            if command.model is not None:
                agent.model = command.model

            if command.timeout_seconds is not None:
                agent.timeout_seconds = command.timeout_seconds

            if command.max_retries is not None:
                agent.max_retries = command.max_retries

            if command.requires_docker is not None:
                agent.requires_docker = command.requires_docker

            if command.requires_dev_container is not None:
                agent.requires_dev_container = command.requires_dev_container

            if command.makes_code_changes is not None:
                agent.makes_code_changes = command.makes_code_changes

            if command.filesystem_write_allowed is not None:
                agent.filesystem_write_allowed = command.filesystem_write_allowed

            agent.updated_at = datetime.now(timezone.utc)

            return agent

    async def add_capability(self, command: AddAgentCapabilityCommand) -> Agent:
        """Add a capability to an agent."""
        with self._lock:
            if command.agent_id not in self._agents:
                raise AgentNotFoundError(command.agent_id)

            agent = self._agents[command.agent_id]

            # Check if capability already exists
            if command.capability.skill in agent.capabilities:
                raise DomainError(
                    f"Capability '{command.capability.skill}' already exists for agent"
                )

            # Add capability
            agent.capabilities[command.capability.skill] = command.capability
            agent.updated_at = datetime.now(timezone.utc)

            return agent

    async def remove_capability(self, command: RemoveAgentCapabilityCommand) -> Agent:
        """Remove a capability from an agent."""
        with self._lock:
            if command.agent_id not in self._agents:
                raise AgentNotFoundError(command.agent_id)

            agent = self._agents[command.agent_id]

            # Check if capability exists
            if command.skill not in agent.capabilities:
                raise DomainError(
                    f"Capability '{command.skill}' not found for agent"
                )

            # Check if it's the last capability
            if len(agent.capabilities) == 1:
                raise DomainError(
                    "Cannot remove the last capability from an agent"
                )

            # Remove capability
            del agent.capabilities[command.skill]
            agent.updated_at = datetime.now(timezone.utc)

            return agent

    async def update_capability(self, command: UpdateAgentCapabilityCommand) -> Agent:
        """Update capability proficiency."""
        with self._lock:
            if command.agent_id not in self._agents:
                raise AgentNotFoundError(command.agent_id)

            agent = self._agents[command.agent_id]

            # Check if capability exists
            if command.skill not in agent.capabilities:
                raise DomainError(
                    f"Capability '{command.skill}' not found for agent"
                )

            # Validate proficiency
            if not 0.0 <= command.proficiency <= 1.0:
                raise DomainError("Proficiency must be between 0.0 and 1.0")

            # Update proficiency
            capability = agent.capabilities[command.skill]
            agent.capabilities[command.skill] = AgentCapability(
                skill=capability.skill,
                proficiency=command.proficiency,
                description=capability.description,
            )
            agent.updated_at = datetime.now(timezone.utc)

            return agent

    async def add_mcp_server(self, command: AddMcpServerCommand) -> Agent:
        """Add an MCP server to agent configuration."""
        with self._lock:
            if command.agent_id not in self._agents:
                raise AgentNotFoundError(command.agent_id)

            agent = self._agents[command.agent_id]

            # Check if server already configured
            if command.server_name in agent.mcp_servers:
                raise DomainError(
                    f"MCP server '{command.server_name}' already configured for agent"
                )

            # Add server
            agent.mcp_servers.append(command.server_name)
            agent.updated_at = datetime.now(timezone.utc)

            return agent

    async def remove_mcp_server(self, command: RemoveMcpServerCommand) -> Agent:
        """Remove an MCP server from agent configuration."""
        with self._lock:
            if command.agent_id not in self._agents:
                raise AgentNotFoundError(command.agent_id)

            agent = self._agents[command.agent_id]

            # Check if server configured
            if command.server_name not in agent.mcp_servers:
                raise DomainError(
                    f"MCP server '{command.server_name}' not configured for agent"
                )

            # Remove server
            agent.mcp_servers.remove(command.server_name)
            agent.updated_at = datetime.now(timezone.utc)

            return agent

    async def delete_agent(self, agent_id: str) -> AgentCommandResult:
        """Delete an agent (soft delete)."""
        with self._lock:
            if agent_id not in self._agents:
                raise AgentNotFoundError(agent_id)

            agent = self._agents[agent_id]

            # Remove from storage
            del self._agents[agent_id]
            del self._agents_by_name[agent.name]

            return AgentCommandResult(
                success=True,
                agent_id=agent_id,
                message=f"Agent '{agent.name}' deleted successfully",
                version=agent._version + 1,
                errors=None,
            )

    def get_agent(self, agent_id: str) -> Agent:
        """
        Helper method to get an agent (for testing).

        Args:
            agent_id: Agent ID

        Returns:
            Agent domain model

        Raises:
            AgentNotFoundError: If agent not found
        """
        with self._lock:
            if agent_id not in self._agents:
                raise AgentNotFoundError(agent_id)
            return self._agents[agent_id]

    def clear(self):
        """Clear all agents (useful for testing)."""
        with self._lock:
            self._agents.clear()
            self._agents_by_name.clear()
