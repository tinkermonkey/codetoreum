"""IAgentRepository output port."""

from abc import ABC, abstractmethod

from codetoreum.domain.agent import Agent


class IAgentRepository(ABC):
    """Repository interface for Agent domain objects."""

    @abstractmethod
    async def get_by_id(self, agent_id: str) -> Agent:
        """Get agent by ID.

        Args:
            agent_id: Unique identifier for the agent

        Returns:
            Agent domain object

        Raises:
            ResourceNotFoundError: If agent not found
        """

    @abstractmethod
    async def get_by_name(self, name: str) -> Agent:
        """Get agent by name.

        Args:
            name: Agent name

        Returns:
            Agent domain object

        Raises:
            ResourceNotFoundError: If agent not found
        """

    @abstractmethod
    async def save(self, agent: Agent) -> None:
        """Persist an agent.

        Args:
            agent: Agent domain object to persist
        """

    @abstractmethod
    async def list_by_project(self, project_id: str) -> list[Agent]:
        """List all agents for a project.

        Args:
            project_id: Project identifier

        Returns:
            List of Agent domain objects for the project
        """
