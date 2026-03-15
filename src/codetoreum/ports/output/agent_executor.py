"""Port interface for agent execution."""

from abc import ABC, abstractmethod


class IAgentExecutor(ABC):
    """Port for triggering and managing agent execution.

    Abstracts the mechanism for executing agents on work items,
    allowing different implementations (in-process, queued, containerized, etc.).
    """

    @abstractmethod
    async def execute(self, work_item_id: str, agent_id: str, board_id: str | None = None) -> None:
        """Execute an agent on a work item.

        Args:
            work_item_id: ID of the work item to process
            agent_id: ID of the agent to execute
            board_id: ID of the board containing the work item (optional, uses default if None)

        Raises:
            Exception: If agent execution fails (logs but doesn't re-raise)
        """
