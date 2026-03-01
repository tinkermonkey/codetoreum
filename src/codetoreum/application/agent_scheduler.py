"""Agent Scheduler application service."""

import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import Enum
from typing import Any

from codetoreum.domain.agent import Agent
from codetoreum.domain.work_item import WorkItem, WorkItemPriority
from codetoreum.infrastructure.observability.instrumentation import (
    instrument_async_function,
)
from codetoreum.ports.exceptions import PortError
from codetoreum.ports.output import IEventStore

logger = logging.getLogger(__name__)


class ScheduleAction(Enum):
    """Actions resulting from scheduling attempt."""

    QUEUED = "queued"
    THROTTLED = "throttled"
    RESOURCE_UNAVAILABLE = "resource_unavailable"
    REJECTED = "rejected"


@dataclass
class ScheduleResult:
    """Result of scheduling operation."""

    success: bool
    action: ScheduleAction
    task_id: str | None
    reason: str
    retry_after: int | None = None  # Seconds to wait before retry


@dataclass
class Task:
    """Task for agent execution."""

    id: str
    agent: str
    project: str
    priority: WorkItemPriority
    context: dict[str, Any]
    created_at: datetime


@dataclass
class AgentConfig:
    """Agent configuration."""

    id: str
    name: str
    max_concurrent: int
    requires_dev_container: bool
    rate_limit_rpm: int | None  # Requests per minute


# Port interfaces
class ITaskQueue:
    """Interface to task queue."""

    async def enqueue(self, task: Task) -> str:
        """Enqueue a task and return task_id."""
        raise NotImplementedError

    async def get_queue_depth(self, agent: str) -> int:
        """Get number of queued tasks for agent."""
        raise NotImplementedError


class IResourceMonitor:
    """Interface to resource availability monitoring."""

    async def check_dev_container_available(self, project: str) -> bool:
        """Check if dev container is available for project."""
        raise NotImplementedError

    async def get_running_agents(self, agent: str) -> int:
        """Get number of currently running instances of agent."""
        raise NotImplementedError


class IRateLimiter:
    """Interface to rate limiting."""

    async def acquire(self, agent: str, tokens: int = 1) -> bool:
        """
        Try to acquire rate limit tokens.

        Returns:
            True if tokens acquired, False if rate limited
        """
        raise NotImplementedError

    async def get_retry_after(self, agent: str) -> int | None:
        """Get seconds to wait before retry."""
        raise NotImplementedError


class IProjectConfiguration:
    """Interface to configuration system."""

    async def get_agent_config(self, agent_name: str) -> AgentConfig:
        """Get agent configuration."""
        raise NotImplementedError


class ISchedulingEvents:
    """Interface for scheduling event emission."""

    async def emit_task_queued(
        self,
        task_id: str,
        agent: str,
        project: str,
        priority: WorkItemPriority,
        reason: str,
    ) -> None:
        """Emit task queued event."""
        raise NotImplementedError

    async def emit_task_throttled(self, agent: str, project: str, reason: str, retry_after: int) -> None:
        """Emit task throttled event."""
        raise NotImplementedError

    async def emit_task_rejected(self, agent: str, project: str, reason: str) -> None:
        """Emit task rejected event."""
        raise NotImplementedError


class AgentScheduler:
    """
    Agent Scheduler application service.

    Manages agent execution scheduling with priority-based queuing,
    resource availability checking, and rate limiting.
    """

    def __init__(
        self,
        task_queue: ITaskQueue,
        resource_monitor: IResourceMonitor,
        rate_limiter: IRateLimiter,
        config: IProjectConfiguration,
        scheduling_events: ISchedulingEvents,
        event_store: IEventStore,
    ):
        """
        Initialize agent scheduler.

        Args:
            task_queue: Task queue for enqueueing agent work
            resource_monitor: Resource availability monitoring
            rate_limiter: Rate limiting for agent executions
            config: Configuration service for agent settings
            scheduling_events: Scheduling event emission
            event_store: Event store for domain events
        """
        self.task_queue = task_queue
        self.resource_monitor = resource_monitor
        self.rate_limiter = rate_limiter
        self.config = config
        self.scheduling_events = scheduling_events
        self.event_store = event_store

    @instrument_async_function(
        name="agent.schedule_execution",
        attributes={"service": "agent_scheduler", "operation": "schedule"},
    )
    async def schedule(self, work_item: WorkItem, agent: Agent, priority: WorkItemPriority) -> ScheduleResult:
        """
        Schedule agent execution for work item.

        Scheduling Flow:
        1. Load agent configuration
        2. Check rate limits
        3. Check resource availability (dev containers, concurrency)
        4. Calculate priority score
        5. Enqueue task if all checks pass
        6. Emit scheduling event

        Args:
            work_item: Work item to be processed
            agent: Agent to execute the work
            priority: Task priority

        Returns:
            ScheduleResult indicating success and action taken
        """
        logger.info(f"Scheduling agent {agent.id} for work item {work_item.id} with priority {priority}")

        # Load agent configuration
        try:
            agent_config = await self.config.get_agent_config(agent.id)
        except PortError as e:
            logger.error(
                f"Failed to load agent config: {e}",
                exc_info=True,
                extra={"error_id": "ERR_SCHEDULER_AGENT_CONFIG_LOAD_FAILURE"},
            )
            await self.scheduling_events.emit_task_rejected(agent.id, work_item.project_id, f"Config error: {e}")
            return ScheduleResult(
                success=False,
                action=ScheduleAction.REJECTED,
                task_id=None,
                reason=f"Failed to load agent config: {e}",
            )

        # Check rate limits
        if agent_config.rate_limit_rpm:
            can_acquire = await self.rate_limiter.acquire(agent.id)
            if not can_acquire:
                retry_after = await self.rate_limiter.get_retry_after(agent.id)
                logger.warning(
                    f"Agent {agent.id} rate limited, retry after {retry_after}s",
                    extra={"error_id": "ERR_SCHEDULER_RATE_LIMIT"},
                )
                await self.scheduling_events.emit_task_throttled(
                    agent.id,
                    work_item.project_id,
                    "Rate limit exceeded",
                    retry_after or 60,
                )
                return ScheduleResult(
                    success=False,
                    action=ScheduleAction.THROTTLED,
                    task_id=None,
                    reason="Rate limit exceeded",
                    retry_after=retry_after,
                )

        # Check resource availability
        can_run = await self.can_schedule(agent_config, work_item.project_id)
        if not can_run:
            reason = await self._get_unavailability_reason(agent_config, work_item.project_id)
            logger.warning(
                f"Cannot schedule agent {agent.id}: {reason}",
                extra={"error_id": "ERR_SCHEDULER_RESOURCE_UNAVAILABLE"},
            )
            await self.scheduling_events.emit_task_rejected(agent.id, work_item.project_id, reason)
            return ScheduleResult(
                success=False,
                action=ScheduleAction.RESOURCE_UNAVAILABLE,
                task_id=None,
                reason=reason,
            )

        # Create task
        task = Task(
            id=f"{work_item.project_id}_{work_item.id}_{agent.id}_{int(datetime.now(UTC).timestamp())}",
            agent=agent.id,
            project=work_item.project_id,
            priority=priority,
            context={
                "work_item_id": work_item.id,
                "work_item_title": work_item.title,
                "work_item_description": work_item.description,
                "work_item_labels": work_item.labels,
                "current_stage": work_item.current_stage,
                "workflow_id": work_item.current_workflow_id,
            },
            created_at=datetime.now(UTC),
        )

        # Enqueue task
        try:
            task_id = await self.task_queue.enqueue(task)
            logger.info(f"Enqueued task {task_id} for agent {agent.id}")
        except PortError as e:
            logger.error(
                f"Failed to enqueue task: {e}",
                exc_info=True,
                extra={"error_id": "ERR_SCHEDULER_ENQUEUE_FAILURE"},
            )
            await self.scheduling_events.emit_task_rejected(agent.id, work_item.project_id, f"Queue error: {e}")
            return ScheduleResult(
                success=False,
                action=ScheduleAction.REJECTED,
                task_id=None,
                reason=f"Failed to enqueue task: {e}",
            )

        # Emit scheduling event
        await self.scheduling_events.emit_task_queued(
            task_id, agent.id, work_item.project_id, priority, "Task scheduled"
        )

        logger.info(f"Successfully scheduled task {task_id} for agent {agent.id}")
        return ScheduleResult(
            success=True,
            action=ScheduleAction.QUEUED,
            task_id=task_id,
            reason="Task successfully queued",
        )

    @instrument_async_function(
        name="agent.check_scheduling_capability",
        attributes={"service": "agent_scheduler", "operation": "check_capability"},
    )
    async def can_schedule(self, agent_config: AgentConfig, project: str) -> bool:
        """
        Check if agent can be scheduled (resource availability).

        Checks:
        1. Dev container availability (if required)
        2. Concurrency limits not exceeded

        Args:
            agent_config: Agent configuration
            project: Project identifier

        Returns:
            True if agent can be scheduled
        """
        # Check dev container availability
        if agent_config.requires_dev_container:
            dev_container_available = await self.resource_monitor.check_dev_container_available(project)
            if not dev_container_available:
                logger.debug(f"Dev container not available for project {project}")
                return False

        # Check concurrency limits
        running_count = await self.resource_monitor.get_running_agents(agent_config.id)
        if running_count >= agent_config.max_concurrent:
            logger.debug(f"Agent {agent_config.id} at max concurrency ({running_count}/{agent_config.max_concurrent})")
            return False

        return True

    @instrument_async_function(
        name="agent.get_queue_depth",
        attributes={"service": "agent_scheduler", "operation": "get_depth"},
    )
    async def get_queue_depth(self, agent: str) -> int:
        """
        Get number of queued tasks for agent.

        Args:
            agent: Agent identifier

        Returns:
            Number of queued tasks
        """
        return await self.task_queue.get_queue_depth(agent)

    async def _get_unavailability_reason(self, agent_config: AgentConfig, project: str) -> str:
        """Get reason why agent cannot be scheduled."""
        # Check dev container
        if agent_config.requires_dev_container:
            dev_container_available = await self.resource_monitor.check_dev_container_available(project)
            if not dev_container_available:
                return f"Dev container not available for project {project}"

        # Check concurrency
        running_count = await self.resource_monitor.get_running_agents(agent_config.id)
        if running_count >= agent_config.max_concurrent:
            return f"Agent at max concurrency ({running_count}/{agent_config.max_concurrent})"

        return "Unknown resource constraint"


# Mock implementations for testing


class InMemoryTaskQueue(ITaskQueue):
    """In-memory task queue for testing."""

    def __init__(self) -> None:
        self.tasks: dict[str, Task] = {}
        self.queue_by_agent: dict[str, int] = {}

    async def enqueue(self, task: Task) -> str:
        """Enqueue a task."""
        self.tasks[task.id] = task
        self.queue_by_agent[task.agent] = self.queue_by_agent.get(task.agent, 0) + 1
        return task.id

    async def get_queue_depth(self, agent: str) -> int:
        """Get queue depth for agent."""
        return self.queue_by_agent.get(agent, 0)


class MockResourceMonitor(IResourceMonitor):
    """Mock resource monitor for testing."""

    def __init__(
        self,
        dev_containers_available: dict[str, bool] | None = None,
        running_agents: dict[str, int] | None = None,
    ):
        self.dev_containers_available = dev_containers_available or {}
        self.running_agents = running_agents or {}

    async def check_dev_container_available(self, project: str) -> bool:
        """Check if dev container available."""
        return self.dev_containers_available.get(project, True)

    async def get_running_agents(self, agent: str) -> int:
        """Get running agent count."""
        return self.running_agents.get(agent, 0)


class MockRateLimiter(IRateLimiter):
    """Mock rate limiter for testing."""

    def __init__(self, rate_limited_agents: dict[str, bool] | None = None):
        self.rate_limited_agents = rate_limited_agents or {}
        self.retry_after_seconds = 60

    async def acquire(self, agent: str, tokens: int = 1) -> bool:
        """Try to acquire tokens."""
        return not self.rate_limited_agents.get(agent, False)

    async def get_retry_after(self, agent: str) -> int | None:
        """Get retry after seconds."""
        if self.rate_limited_agents.get(agent, False):
            return self.retry_after_seconds
        return None


class MockProjectConfiguration(IProjectConfiguration):
    """Mock project configuration for testing."""

    def __init__(self, agents: dict[str, AgentConfig] | None = None):
        self.agents = agents or {}

    async def get_agent_config(self, agent_name: str) -> AgentConfig:
        """Get agent config."""
        if agent_name not in self.agents:
            # Return default config
            return AgentConfig(
                id=agent_name,
                name=agent_name,
                max_concurrent=3,
                requires_dev_container=False,
                rate_limit_rpm=None,
            )
        return self.agents[agent_name]


class MockSchedulingEvents(ISchedulingEvents):
    """Mock scheduling events for testing."""

    def __init__(self) -> None:
        self.queued_events: list = []
        self.throttled_events: list = []
        self.rejected_events: list = []

    async def emit_task_queued(
        self,
        task_id: str,
        agent: str,
        project: str,
        priority: WorkItemPriority,
        reason: str,
    ) -> None:
        """Emit task queued event."""
        self.queued_events.append(
            {
                "task_id": task_id,
                "agent": agent,
                "project": project,
                "priority": priority,
                "reason": reason,
            }
        )

    async def emit_task_throttled(self, agent: str, project: str, reason: str, retry_after: int) -> None:
        """Emit task throttled event."""
        self.throttled_events.append(
            {
                "agent": agent,
                "project": project,
                "reason": reason,
                "retry_after": retry_after,
            }
        )

    async def emit_task_rejected(self, agent: str, project: str, reason: str) -> None:
        """Emit task rejected event."""
        self.rejected_events.append({"agent": agent, "project": project, "reason": reason})
