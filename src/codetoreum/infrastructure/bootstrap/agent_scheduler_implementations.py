import logging

from codetoreum.application.agent_scheduler import (
    AgentConfig,
    IProjectConfiguration,
    IRateLimiter,
    IResourceMonitor,
    ISchedulingEvents,
    WorkItemPriority,
)

logger = logging.getLogger(__name__)


class ProductionResourceMonitor(IResourceMonitor):
    """MVP resource monitor — assumes sufficient resources available."""

    async def check_dev_container_available(self, project: str) -> bool:
        logger.debug(f"Resource check: dev container available for {project}")
        return True

    async def get_running_agents(self, agent: str) -> int:
        logger.debug(f"Resource check: {agent} has 0 running instances")
        return 0


class ProductionRateLimiter(IRateLimiter):
    """MVP rate limiter — allows all requests."""

    async def acquire(self, agent: str, tokens: int = 1) -> bool:
        logger.debug(f"Rate limit: acquired {tokens} token(s) for {agent}")
        return True

    async def get_retry_after(self, agent: str) -> int | None:
        return None


class ProductionProjectConfiguration(IProjectConfiguration):
    """MVP configuration service — returns default agent configs."""

    async def get_agent_config(self, agent_name: str) -> AgentConfig:
        config = AgentConfig(
            id=agent_name,
            name=agent_name,
            max_concurrent=3,
            requires_dev_container=False,
            rate_limit_rpm=None,
        )
        logger.debug(f"Configuration: {agent_name} config loaded (MVP defaults)")
        return config


class ProductionSchedulingEvents(ISchedulingEvents):
    """MVP scheduling events — logs but does not emit to event bus."""

    async def emit_task_queued(
        self,
        task_id: str,
        agent: str,
        project: str,
        priority: WorkItemPriority,
        reason: str,
    ) -> None:
        logger.info(f"Task queued: {task_id} ({agent}/{project}, priority={priority}, reason={reason})")

    async def emit_task_throttled(self, agent: str, project: str, reason: str, retry_after: int) -> None:
        logger.warning(f"Task throttled: {agent}/{project} (reason={reason}, retry_after={retry_after}s)")

    async def emit_task_rejected(self, agent: str, project: str, reason: str) -> None:
        logger.error(f"Task rejected: {agent}/{project} (reason={reason})")
