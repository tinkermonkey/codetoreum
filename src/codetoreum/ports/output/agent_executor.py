"""Port interface for agent execution."""

from abc import ABC, abstractmethod
from collections.abc import Callable, Coroutine
from typing import Any


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

    @abstractmethod
    def set_completion_handler(
        self,
        callback: Callable[[str, str, bool], Coroutine[Any, Any, None]],
        default_board_id: str,
    ) -> None:
        """Wire completion callback for agent execution.

        Called after the executor is created, when the completion callback becomes available.
        This avoids circular constructor dependencies between the executor and the event handler.

        Args:
            callback: Async function(work_item_id, board_id, success) invoked when execution completes
            default_board_id: Board ID to pass to callback when none is provided to execute()

        Raises:
            RuntimeError: If called after execution has started
        """
