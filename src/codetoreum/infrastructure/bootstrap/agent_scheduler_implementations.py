"""Production implementations for AgentScheduler dependencies.

These are MVP in-memory implementations that provide basic functionality
without external dependencies. Post-MVP should integrate with proper
resource monitoring, configuration services, and event systems.
"""

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
    """
    Production resource monitor for MVP.

    Assumes sufficient resources are available (containers, agents) during MVP phase.
    Post-MVP should integrate with Docker/Kubernetes monitoring.
    """

    async def check_dev_container_available(self, project: str) -> bool:
        """Check if dev container is available for project."""
        # MVP: Assume containers are available
        logger.debug(f"Resource check: dev container available for {project}")
        return True

    async def get_running_agents(self, agent: str) -> int:
        """Get number of currently running instances of agent."""
        # MVP: Assume no agents running (capacity available)
        logger.debug(f"Resource check: {agent} has 0 running instances")
        return 0


class ProductionRateLimiter(IRateLimiter):
    """
    Production rate limiter for MVP.

    Allows all requests during MVP. Post-MVP should enforce actual rate limits
    based on external API quotas and configured limits per agent.
    """

    async def acquire(self, agent: str, tokens: int = 1) -> bool:
        """
        Try to acquire rate limit tokens.

        MVP: Always returns True (no actual rate limiting).
        Post-MVP: Implement token bucket or sliding window algorithm.
        """
        logger.debug(f"Rate limit: acquired {tokens} token(s) for {agent}")
        return True

    async def get_retry_after(self, agent: str) -> int | None:
        """Get retry after seconds (MVP: never rate limited)."""
        return None


class ProductionProjectConfiguration(IProjectConfiguration):
    """
    Production project configuration service for MVP.

    Provides default agent configurations. Post-MVP should fetch from
    configuration store or database.
    """

    async def get_agent_config(self, agent_name: str) -> AgentConfig:
        """
        Get agent configuration.

        MVP: Returns sensible defaults for all agents.
        Post-MVP: Load from ConfigurationService.
        """
        config = AgentConfig(
            id=agent_name,
            name=agent_name,
            max_concurrent=3,  # MVP default: allow 3 concurrent executions
            requires_dev_container=False,  # MVP: general agents, no special containers
            rate_limit_rpm=None,  # MVP: no rate limiting
        )
        logger.debug(f"Configuration: {agent_name} config loaded (MVP defaults)")
        return config


class ProductionSchedulingEvents(ISchedulingEvents):
    """
    Production scheduling events emitter for MVP.

    Logs scheduling events but does not emit to event bus (post-MVP feature).
    Post-MVP: Integrate with EventBus to emit proper domain events.
    """

    async def emit_task_queued(
        self,
        task_id: str,
        agent: str,
        project: str,
        priority: WorkItemPriority,
        reason: str,
    ) -> None:
        """Emit task queued event."""
        logger.info(f"Task queued: {task_id} ({agent}/{project}, priority={priority}, reason={reason})")
        # MVP: Log only, do not emit to event bus
        # Post-MVP: Emit to event bus for audit trail and downstream processing

    async def emit_task_throttled(self, agent: str, project: str, reason: str, retry_after: int) -> None:
        """Emit task throttled event."""
        logger.warning(f"Task throttled: {agent}/{project} (reason={reason}, retry_after={retry_after}s)")
        # MVP: Log only
        # Post-MVP: Emit to event bus

    async def emit_task_rejected(self, agent: str, project: str, reason: str) -> None:
        """Emit task rejected event."""
        logger.error(f"Task rejected: {agent}/{project} (reason={reason})")
        # MVP: Log only
        # Post-MVP: Emit to event bus
