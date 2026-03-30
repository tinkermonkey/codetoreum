"""In-memory agent repository for testing and simulation."""

from codetoreum.domain.agent import Agent
from codetoreum.ports.exceptions import ResourceNotFoundError
from codetoreum.ports.output.agent_repository import IAgentRepository


class InMemoryAgentRepository(IAgentRepository):
    """In-memory implementation of IAgentRepository for testing.

    Stores agents by ID and by name. Also supports project-scoped lookups
    via the save_for_project() helper.
    """

    def __init__(self) -> None:
        """Initialize the in-memory agent repository."""
        self._agents_by_id: dict[str, Agent] = {}
        self._agents_by_name: dict[str, Agent] = {}
        # project_id -> set of agent IDs
        self._project_agents: dict[str, set[str]] = {}

    async def get_by_id(self, agent_id: str) -> Agent:
        """Get agent by ID.

        Args:
            agent_id: Unique identifier for the agent

        Returns:
            Agent domain object

        Raises:
            ResourceNotFoundError: If agent not found
        """
        if agent_id not in self._agents_by_id:
            raise ResourceNotFoundError("Agent", agent_id)
        return self._agents_by_id[agent_id]

    async def get_by_name(self, name: str) -> Agent:
        """Get agent by name.

        Args:
            name: Agent name

        Returns:
            Agent domain object

        Raises:
            ResourceNotFoundError: If agent not found
        """
        if name not in self._agents_by_name:
            raise ResourceNotFoundError("Agent", name)
        return self._agents_by_name[name]

    async def save(self, agent: Agent, project_id: str | None = None) -> None:
        """Persist an agent.

        Args:
            agent: Agent domain object to persist
            project_id: Optional project to associate the agent with
        """
        self._agents_by_id[agent.id] = agent
        self._agents_by_name[agent.name] = agent
        if project_id:
            self._project_agents.setdefault(project_id, set()).add(agent.id)

    async def list_by_project(self, project_id: str) -> list[Agent]:
        """List all agents for a project.

        Args:
            project_id: Project identifier

        Returns:
            List of Agent domain objects for the project
        """
        agent_ids = self._project_agents.get(project_id, set())
        return [self._agents_by_id[aid] for aid in agent_ids if aid in self._agents_by_id]

    async def save_for_project(self, project_id: str, agent: Agent) -> None:
        """Save an agent and associate it with a project.

        Helper method for test setup that persists the agent and registers
        the project association.

        Args:
            project_id: Project identifier
            agent: Agent domain object to persist
        """
        await self.save(agent, project_id)

    async def get_all(self) -> list[Agent]:
        """Get all agents in the repository.

        Returns:
            List of all Agent domain objects
        """
        return list(self._agents_by_id.values())

    def get_all_sync(self) -> list[Agent]:
        """Get all agents in the repository synchronously.

        This is a synchronous version of get_all() for use during adapter
        initialization when we need to populate caches without async/await.
        InMemoryAgentRepository stores agents in memory, so this is safe.

        Returns:
            List of all Agent domain objects
        """
        return list(self._agents_by_id.values())

    def get_by_name_sync(self, name: str) -> Agent:
        """Get agent by name synchronously.

        This is a synchronous version of get_by_name() for use in contexts
        where async/await is not available. InMemoryAgentRepository stores
        agents in memory, so this is safe to call synchronously.

        Args:
            name: Agent name

        Returns:
            Agent domain object

        Raises:
            ResourceNotFoundError: If agent not found
        """
        if name not in self._agents_by_name:
            raise ResourceNotFoundError("Agent", name)
        return self._agents_by_name[name]
