"""
Agent Command Port Interface

Defines the contract for agent registry command operations.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Dict, List, Optional

from codetoreum.domain.agent import Agent, AgentCapability, AgentType

# ============================================================================
# Commands
# ============================================================================


@dataclass
class CreateAgentCommand:
    """Command to create a new agent."""

    name: str
    display_name: str
    agent_type: AgentType
    role_description: str
    model: str
    capabilities: Dict[str, AgentCapability]
    timeout_seconds: int = 300
    max_retries: int = 3
    requires_docker: bool = True
    requires_dev_container: bool = False
    makes_code_changes: bool = False
    filesystem_write_allowed: bool = True
    mcp_servers: Optional[List[str]] = None


@dataclass
class UpdateAgentCommand:
    """Command to update an existing agent."""

    agent_id: str
    display_name: Optional[str] = None
    role_description: Optional[str] = None
    model: Optional[str] = None
    timeout_seconds: Optional[int] = None
    max_retries: Optional[int] = None
    requires_docker: Optional[bool] = None
    requires_dev_container: Optional[bool] = None
    makes_code_changes: Optional[bool] = None
    filesystem_write_allowed: Optional[bool] = None


@dataclass
class AddAgentCapabilityCommand:
    """Command to add a capability to an agent."""

    agent_id: str
    capability: AgentCapability


@dataclass
class RemoveAgentCapabilityCommand:
    """Command to remove a capability from an agent."""

    agent_id: str
    skill: str


@dataclass
class UpdateAgentCapabilityCommand:
    """Command to update capability proficiency."""

    agent_id: str
    skill: str
    proficiency: float


@dataclass
class AddMcpServerCommand:
    """Command to add an MCP server to agent configuration."""

    agent_id: str
    server_name: str


@dataclass
class RemoveMcpServerCommand:
    """Command to remove an MCP server from agent configuration."""

    agent_id: str
    server_name: str


# ============================================================================
# Result Models
# ============================================================================


@dataclass
class AgentCommandResult:
    """Result from agent command operations."""

    success: bool
    agent_id: str
    message: str
    version: int
    errors: Optional[List[str]] = None


# ============================================================================
# Port Interface
# ============================================================================


class IAgentCommandPort(ABC):
    """
    Agent Command Input Port.

    Provides write operations for agent registry management.
    """

    @abstractmethod
    async def create_agent(self, command: CreateAgentCommand) -> Agent:
        """
        Create a new agent.

        Args:
            command: CreateAgentCommand with agent details

        Returns:
            Created Agent domain model

        Raises:
            DomainError: If agent with same name already exists or validation fails
        """
        pass

    @abstractmethod
    async def update_agent(self, command: UpdateAgentCommand) -> Agent:
        """
        Update an existing agent.

        Args:
            command: UpdateAgentCommand with fields to update

        Returns:
            Updated Agent domain model

        Raises:
            AgentNotFoundError: If agent doesn't exist
            DomainError: If validation fails
        """
        pass

    @abstractmethod
    async def add_capability(self, command: AddAgentCapabilityCommand) -> Agent:
        """
        Add a capability to an agent.

        Args:
            command: AddAgentCapabilityCommand with capability details

        Returns:
            Updated Agent domain model

        Raises:
            AgentNotFoundError: If agent doesn't exist
            DomainError: If capability already exists or validation fails
        """
        pass

    @abstractmethod
    async def remove_capability(self, command: RemoveAgentCapabilityCommand) -> Agent:
        """
        Remove a capability from an agent.

        Args:
            command: RemoveAgentCapabilityCommand with skill to remove

        Returns:
            Updated Agent domain model

        Raises:
            AgentNotFoundError: If agent doesn't exist
            DomainError: If capability doesn't exist or it's the last capability
        """
        pass

    @abstractmethod
    async def update_capability(self, command: UpdateAgentCapabilityCommand) -> Agent:
        """
        Update capability proficiency.

        Args:
            command: UpdateAgentCapabilityCommand with updated proficiency

        Returns:
            Updated Agent domain model

        Raises:
            AgentNotFoundError: If agent doesn't exist
            DomainError: If capability doesn't exist or proficiency is invalid
        """
        pass

    @abstractmethod
    async def add_mcp_server(self, command: AddMcpServerCommand) -> Agent:
        """
        Add an MCP server to agent configuration.

        Args:
            command: AddMcpServerCommand with server name

        Returns:
            Updated Agent domain model

        Raises:
            AgentNotFoundError: If agent doesn't exist
            DomainError: If server already configured
        """
        pass

    @abstractmethod
    async def remove_mcp_server(self, command: RemoveMcpServerCommand) -> Agent:
        """
        Remove an MCP server from agent configuration.

        Args:
            command: RemoveMcpServerCommand with server name

        Returns:
            Updated Agent domain model

        Raises:
            AgentNotFoundError: If agent doesn't exist
            DomainError: If server not configured
        """
        pass

    @abstractmethod
    async def delete_agent(self, agent_id: str) -> AgentCommandResult:
        """
        Delete an agent (soft delete).

        Args:
            agent_id: Agent ID

        Returns:
            AgentCommandResult with operation status

        Raises:
            AgentNotFoundError: If agent doesn't exist
        """
        pass
