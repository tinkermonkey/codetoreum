"""Resilience factory.

Creates resilient adapters with appropriate components based on operation mode.
"""

from typing import Any

from codetoreum.ports.output.container import IContainer
from codetoreum.ports.output.repository import IRepository
from codetoreum.ports.output.ticket_system import ITicketSystem
from codetoreum.ports.output.version_control_service import IVersionControlService
from codetoreum.ports.output.work_execution_state_tracker import (
    IWorkExecutionStateTracker,
)

from .circuit_breaker import CircuitBreaker
from .config import (
    GITHUB_RESILIENCE_CONFIG,
    OperationMode,
)
from .decorators import (
    BestEffortExecutionTrackerDecorator,
    ResilientTicketSystemDecorator,
)
from .mocks import MockCircuitBreaker, MockRateLimiter, MockRetryPolicy, MockTimeout
from .rate_limiter import TokenBucketRateLimiter
from .retry_policy import ExponentialBackoffRetry
from .timeout import AsyncTimeout


class ResilienceFactory:
    """
    Creates resilient adapters with appropriate components.

    Switches between production and mock implementations based on mode.
    """

    def __init__(self, mode: OperationMode = OperationMode.PRODUCTION, config: dict[str, Any] | None = None):
        """
        Initialize factory.

        Args:
            mode: Operation mode (production, simulation, integration_test)
            config: Configuration overrides
        """
        self.mode = mode
        self.config = config or {}

    def create_resilient_ticket_system(
        self, adapter: ITicketSystem, service_config: dict[str, Any] | None = None
    ) -> ITicketSystem:
        """
        Create resilient ticket system adapter.

        Args:
            adapter: Underlying ticket system adapter (GitHub, Jira, etc.)
            service_config: Service-specific configuration

        Returns:
            ITicketSystem: Wrapped adapter with resilience
        """
        cfg = {**self.config, **(service_config or {})}

        # Create components based on mode
        if self.mode == OperationMode.PRODUCTION:
            rate_limiter = TokenBucketRateLimiter(
                max_requests=cfg.get(
                    "max_requests",
                    GITHUB_RESILIENCE_CONFIG.rate_limit.max_requests if GITHUB_RESILIENCE_CONFIG.rate_limit else 5000,
                ),
                window_seconds=cfg.get("window_seconds", 3600),
                max_wait_seconds=cfg.get("max_wait_seconds", 60),
            )

            circuit_breaker = CircuitBreaker(
                failure_threshold=cfg.get("failure_threshold", 5),
                timeout_seconds=cfg.get("circuit_timeout_seconds", 60),
                success_threshold=cfg.get("success_threshold", 2),
            )

            retry_policy = ExponentialBackoffRetry(
                max_retries=cfg.get("max_retries", 3),
                base_delay=cfg.get("base_delay", 1.0),
                max_delay=cfg.get("max_delay", 60.0),
            )

            timeout = AsyncTimeout()

        elif self.mode == OperationMode.SIMULATION:
            # Mock components with no delays
            rate_limiter = MockRateLimiter(enforce_limits=False)
            circuit_breaker = MockCircuitBreaker()
            retry_policy = MockRetryPolicy(simulate_retries=False)
            timeout = MockTimeout(simulate_timeouts=False)

        else:  # INTEGRATION_TEST
            # Mock components but enforce limits for realistic testing
            rate_limiter = MockRateLimiter(enforce_limits=True)
            circuit_breaker = CircuitBreaker(failure_threshold=3, timeout_seconds=5)
            retry_policy = MockRetryPolicy(simulate_retries=True, max_retries=2)
            timeout = AsyncTimeout()

        return ResilientTicketSystemDecorator(
            wrapped=adapter,
            rate_limiter=rate_limiter,
            circuit_breaker=circuit_breaker,
            retry_policy=retry_policy,
            timeout=timeout,
            default_timeout_seconds=cfg.get("default_timeout", 30.0),
        )

    def create_resilient_repository(
        self, adapter: IRepository, service_config: dict[str, Any] | None = None
    ) -> IRepository:
        """
        Create resilient repository adapter.

        Note: This would need a ResilientRepositoryDecorator implementation.
        For now, returning the adapter as-is as a placeholder.

        Args:
            adapter: Underlying repository adapter
            service_config: Service-specific configuration

        Returns:
            IRepository: Adapter (unwrapped placeholder)
        """
        # TODO: Implement ResilientRepositoryDecorator
        # Similar pattern to ResilientTicketSystemDecorator
        return adapter

    def create_resilient_container(
        self, adapter: IContainer, service_config: dict[str, Any] | None = None
    ) -> IContainer:
        """
        Create resilient container adapter.

        Note: This would need a ResilientContainerDecorator implementation.
        For now, returning the adapter as-is as a placeholder.

        Args:
            adapter: Underlying container adapter
            service_config: Service-specific configuration

        Returns:
            IContainer: Adapter (unwrapped placeholder)
        """
        # TODO: Implement ResilientContainerDecorator
        # Similar pattern to ResilientTicketSystemDecorator
        return adapter

    def create_resilient_version_control(
        self, adapter: IVersionControlService, service_config: dict[str, Any] | None = None
    ) -> IVersionControlService:
        """
        Create resilient version control adapter.

        Note: This would need a ResilientVersionControlDecorator implementation.
        For now, returning the adapter as-is as a placeholder.

        Args:
            adapter: Underlying version control adapter
            service_config: Service-specific configuration

        Returns:
            IVersionControlService: Adapter (unwrapped placeholder)
        """
        # TODO: Implement ResilientVersionControlDecorator
        # Similar pattern to ResilientTicketSystemDecorator
        return adapter

    def create_best_effort_execution_tracker(
        self, adapter: IWorkExecutionStateTracker
    ) -> IWorkExecutionStateTracker:
        """
        Create best-effort execution state tracker decorator.

        Wraps the tracker with graceful degradation: failures in
        mark_execution_started() are logged but do not block execution.
        The tracker is only a hint store for recovery decisions; failures
        are non-critical since recovery defaults safely to kill if no hint
        is found.

        Args:
            adapter: Underlying execution state tracker adapter

        Returns:
            IWorkExecutionStateTracker: Wrapped adapter with best-effort resilience
        """
        return BestEffortExecutionTrackerDecorator(wrapped=adapter)
