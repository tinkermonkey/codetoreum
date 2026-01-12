"""Port interface for agent execution."""

from abc import ABC, abstractmethod


class IAgentExecutor(ABC):
    """Port for triggering and managing agent execution.

    Abstracts the mechanism for executing agents on work items,
    allowing different implementations (in-process, queued, containerized, etc.).
    """

    @abstractmethod
    async def execute(self, work_item_id: str, agent_id: str) -> None:
        """Execute an agent on a work item.

        Args:
            work_item_id: ID of the work item to process
            agent_id: ID of the agent to execute

        Raises:
            Exception: If agent execution fails (logs but doesn't re-raise)
        """
        pass
