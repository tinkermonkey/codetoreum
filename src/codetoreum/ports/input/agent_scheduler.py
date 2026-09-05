"""IAgentScheduler input port interface.

Schedulers are application services exposed at the input boundary — callers
hand a (work_item, agent, priority) tuple to the scheduler and it returns a
ScheduleResult, then it independently drives execution via its consumer loop.

This port exists primarily to satisfy INV-09 (explicit port inheritance for
application services). The methods listed below are the surface that
production code and tests actually exercise — the AgentScheduler class has
many helper methods that are not part of the contract.

NOTE: As of this change, `dispatch_via_task_queue=False` on
`WorkflowOrchestrator` means the scheduler's consumer loop is dormant in
production — BoardColumnEventHandler owns event-driven dispatch. The port
is defined anyway because the in-memory scheduler is still constructed and
the queue-based dispatch path is a documented "armed but unused" seam that
can be flipped on without touching the port shape.
"""

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    # Domain types are imported lazily to keep ports.input importable from
    # very early bootstrap phases.
    from codetoreum.application.agent_scheduler import ScheduleResult
    from codetoreum.domain.agent import Agent
    from codetoreum.domain.work_item import WorkItem, WorkItemPriority
    from codetoreum.ports.output import IAgentExecutor


class IAgentScheduler(ABC):
    """Application-level scheduling contract for agent executions."""

    @abstractmethod
    async def schedule(
        self,
        work_item: "WorkItem",
        agent: "Agent",
        priority: "WorkItemPriority",
    ) -> "ScheduleResult":
        """Schedule an agent execution.

        Returns a ScheduleResult indicating whether the work was queued,
        throttled, or rejected.
        """

    @abstractmethod
    async def get_queue_depth(self, agent: str) -> int:
        """Return the current queue depth for the given agent."""

    @abstractmethod
    def set_executor(self, executor: "IAgentExecutor") -> None:
        """Wire the executor used by the consumer loop to dispatch queued tasks.

        This is a deferred-injection seam: the executor is built later in
        bootstrap than the scheduler, so it cannot be a constructor argument
        without inverting Phase 5's adapter/service ordering.
        """

    @abstractmethod
    async def start(self) -> None:
        """Start the consumer loop. Idempotent."""

    @abstractmethod
    async def stop(self) -> None:
        """Stop the consumer loop. Idempotent."""


__all__ = ["IAgentScheduler"]
