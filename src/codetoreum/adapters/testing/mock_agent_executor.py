"""Mock agent executor for simulation testing.

Simulates agent execution with configurable delay. When execution completes,
invokes a completion callback that triggers auto-progression to the next
board column via BoardColumnEventHandler.handle_agent_completion().
"""

import asyncio
import logging
from collections.abc import Callable, Coroutine
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any
from uuid import uuid4

from codetoreum.domain.agent_execution import ExecutionStatus
from codetoreum.ports.input.execution_query import ExecutionInfo
from codetoreum.ports.output.agent_executor import IAgentExecutor

if TYPE_CHECKING:
    from codetoreum.adapters.primary.input_port_adapters.mock.mock_execution_query_adapter import (
        MockExecutionQueryAdapter,
    )

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
        self._completion_callback: Callable[[str, str, bool], Coroutine[Any, Any, None]] | None = None
        self._default_board_id = "board-1"
        self._executions: list[dict[str, Any]] = []
        self._pending_tasks: set[asyncio.Task] = set()
        self._execution_query: MockExecutionQueryAdapter | None = None

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

    def set_execution_query(self, adapter: "MockExecutionQueryAdapter") -> None:
        """Wire execution query adapter for UX visibility.

        When set, the executor creates ExecutionInfo records on execute/complete
        so that GET /api/v2/executions returns real data.

        Args:
            adapter: MockExecutionQueryAdapter to push records into
        """
        self._execution_query = adapter

    async def execute(self, work_item_id: str, agent_id: str) -> None:
        """Execute an agent on a work item (fire-and-forget).

        Records the execution and schedules background work via
        asyncio.create_task so the caller is not blocked.

        Args:
            work_item_id: ID of the work item to process
            agent_id: ID of the agent to execute
        """
        execution_id = str(uuid4())
        now = datetime.now(UTC)
        self._executions.append({
            "work_item_id": work_item_id,
            "agent_id": agent_id,
            "started_at": now.isoformat(),
            "execution_id": execution_id,
        })
        logger.info(f"Agent '{agent_id}' started on work item '{work_item_id}'")

        # Push RUNNING record to execution query adapter for UX visibility
        if self._execution_query:
            info = ExecutionInfo(
                id=execution_id,
                agent_id=agent_id,
                agent_name=agent_id,
                work_item_id=work_item_id,
                workflow_id="simulation",
                stage_name=agent_id,
                status=ExecutionStatus.RUNNING,
                container_name=None,
                container_id=None,
                output=None,
                error_message=None,
                error_detail=None,
                exit_code=None,
                input_tokens=0,
                output_tokens=0,
                duration_seconds=None,
                initialized_at=now,
                started_at=now,
                completed_at=None,
            )
            self._execution_query.add_execution(info)

        task = asyncio.create_task(
            self._simulate_execution(work_item_id, agent_id, execution_id, now)
        )
        self._pending_tasks.add(task)
        task.add_done_callback(self._pending_tasks.discard)

    async def _simulate_execution(
        self,
        work_item_id: str,
        agent_id: str,
        execution_id: str,
        started_at: datetime,
    ) -> None:
        """Simulate agent work then invoke completion callback."""
        try:
            await asyncio.sleep(self._execution_delay)
            logger.info(
                f"Agent '{agent_id}' completed on work item '{work_item_id}'"
            )

            # Update execution record to COMPLETED
            self._update_execution_record(
                execution_id, agent_id, work_item_id, started_at,
                ExecutionStatus.COMPLETED,
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

            # Update execution record to FAILED
            self._update_execution_record(
                execution_id, agent_id, work_item_id, started_at,
                ExecutionStatus.FAILED, error_message=str(e),
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

    def _update_execution_record(
        self,
        execution_id: str,
        agent_id: str,
        work_item_id: str,
        started_at: datetime,
        status: ExecutionStatus,
        error_message: str | None = None,
    ) -> None:
        """Replace execution record with final status in the query adapter."""
        if not self._execution_query:
            return
        now = datetime.now(UTC)
        duration = (now - started_at).total_seconds()
        info = ExecutionInfo(
            id=execution_id,
            agent_id=agent_id,
            agent_name=agent_id,
            work_item_id=work_item_id,
            workflow_id="simulation",
            stage_name=agent_id,
            status=status,
            container_name=None,
            container_id=None,
            output=None,
            error_message=error_message,
            error_detail=None,
            exit_code=0 if status == ExecutionStatus.COMPLETED else 1,
            input_tokens=0,
            output_tokens=0,
            duration_seconds=duration,
            initialized_at=started_at,
            started_at=started_at,
            completed_at=now,
        )
        self._execution_query.add_execution(info)

    @property
    def executions(self) -> list[dict[str, Any]]:
        """Return recorded executions for test assertions."""
        return list(self._executions)
