"""Mock agent executor for simulation testing.

Simulates agent execution with configurable delay. When execution completes,
invokes a completion callback that triggers auto-progression to the next
board column via BoardColumnEventHandler.handle_agent_completion().
"""

import asyncio
import logging
from datetime import datetime, timezone
from typing import Any, Callable, Coroutine, Dict, List, Optional

from codetoreum.ports.output.agent_executor import IAgentExecutor

logger = logging.getLogger(__name__)


class MockAgentExecutor(IAgentExecutor):
    """Mock implementation of IAgentExecutor for simulation.

    Simulates agent work by sleeping for a configurable duration, then
    invoking a completion callback. The execute() method returns immediately
    via asyncio.create_task so the event handler is not blocked waiting
    for agent work to finish.

    Attributes:
        _execution_delay: Seconds to simulate agent work
        _completion_callback: Async callback invoked after execution
        _default_board_id: Board ID passed to completion callback
        _executions: Record of all executions for test assertions
    """

    def __init__(self, execution_delay_seconds: float = 3.0):
        self._execution_delay = execution_delay_seconds
        self._completion_callback: Optional[
            Callable[[str, str, bool], Coroutine[Any, Any, None]]
        ] = None
        self._default_board_id = "board-1"
        self._executions: List[Dict[str, Any]] = []
        self._pending_tasks: set[asyncio.Task] = set()

    def set_completion_handler(
        self,
        callback: Callable[[str, str, bool], Coroutine[Any, Any, None]],
        default_board_id: str,
    ) -> None:
        """Wire completion callback after handler creation.

        This avoids circular constructor dependencies: the handler needs the
        executor, and the executor needs the handler's completion method.

        Args:
            callback: Async function(work_item_id, board_id, success)
            default_board_id: Board ID to pass to callback
        """
        self._completion_callback = callback
        self._default_board_id = default_board_id

    async def execute(self, work_item_id: str, agent_id: str) -> None:
        """Execute an agent on a work item (fire-and-forget).

        Records the execution and schedules background work via
        asyncio.create_task so the caller is not blocked.

        Args:
            work_item_id: ID of the work item to process
            agent_id: ID of the agent to execute
        """
        self._executions.append({
            "work_item_id": work_item_id,
            "agent_id": agent_id,
            "started_at": datetime.now(timezone.utc).isoformat(),
        })
        logger.info(f"Agent '{agent_id}' started on work item '{work_item_id}'")
        task = asyncio.create_task(self._simulate_execution(work_item_id, agent_id))
        self._pending_tasks.add(task)
        task.add_done_callback(self._pending_tasks.discard)

    async def _simulate_execution(
        self, work_item_id: str, agent_id: str
    ) -> None:
        """Simulate agent work then invoke completion callback."""
        try:
            await asyncio.sleep(self._execution_delay)
            logger.info(
                f"Agent '{agent_id}' completed on work item '{work_item_id}'"
            )
            if self._completion_callback:
                await self._completion_callback(
                    work_item_id, self._default_board_id, True
                )
            else:
                logger.warning(
                    f"No completion callback set for MockAgentExecutor. "
                    f"Work item '{work_item_id}' completed but auto-progression will not occur."
                )
        except asyncio.CancelledError:
            logger.info(f"Execution cancelled for {work_item_id}")
            raise
        except Exception as e:
            logger.error(
                f"Simulated execution failed for {work_item_id}: {e}",
                exc_info=True,
            )
            if self._completion_callback:
                try:
                    await self._completion_callback(
                        work_item_id, self._default_board_id, False
                    )
                except Exception as cb_err:
                    logger.error(
                        f"Completion callback also failed for {work_item_id}: {cb_err}",
                        exc_info=True,
                    )

    @property
    def executions(self) -> List[Dict[str, Any]]:
        """Return recorded executions for test assertions."""
        return list(self._executions)
