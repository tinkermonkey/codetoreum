"""Health checker implementations.

Provides concrete health check implementations for various system components.
"""

import asyncio
import time
from datetime import datetime
from typing import Dict, List, Optional, Callable

from .interfaces import (
    DependencyHealth,
    HealthCheckResult,
    HealthStatus,
    IHealthCheck,
)
from ..resilience.interfaces import ICircuitBreaker, IRateLimiter, CircuitState


class HealthChecker(IHealthCheck):
    """
    Main health checker implementation.

    Aggregates health checks from multiple dependencies and provides
    liveness and readiness probes.
    """

    def __init__(
        self,
        dependencies: Optional[Dict[str, IHealthCheck]] = None,
        app_name: str = "codetoreum",
        version: str = "unknown"
    ):
        """
        Initialize health checker.

        Args:
            dependencies: Dictionary of dependency name -> health check
            app_name: Application name
            version: Application version
        """
        self.dependencies = dependencies or {}
        self.app_name = app_name
        self.version = version
        self._start_time = time.time()

    async def check_liveness(self) -> HealthCheckResult:
        """
        Check if the application is alive.

        Simple check that doesn't depend on external services.
        """
        return HealthCheckResult(
            status=HealthStatus.HEALTHY,
            message=f"{self.app_name} is alive",
            metadata={
                "app_name": self.app_name,
                "version": self.version,
                "uptime_seconds": time.time() - self._start_time,
            }
        )

    async def check_readiness(self) -> HealthCheckResult:
        """
        Check if the application is ready to serve requests.

        Checks all registered dependencies.
        """
        dependency_results = []
        overall_status = HealthStatus.HEALTHY

        # Check all dependencies in parallel
        tasks = []
        for name, checker in self.dependencies.items():
            tasks.append(self._check_dependency_safe(name, checker))

        dependency_results = await asyncio.gather(*tasks)

        # Determine overall status
        for dep in dependency_results:
            if dep.status == HealthStatus.UNHEALTHY:
                overall_status = HealthStatus.UNHEALTHY
                break
            elif dep.status == HealthStatus.DEGRADED and overall_status == HealthStatus.HEALTHY:
                overall_status = HealthStatus.DEGRADED

        message = self._generate_readiness_message(overall_status, dependency_results)

        return HealthCheckResult(
            status=overall_status,
            message=message,
            dependencies=dependency_results,
            metadata={
                "app_name": self.app_name,
                "version": self.version,
                "total_dependencies": len(self.dependencies),
                "healthy_dependencies": sum(1 for d in dependency_results if d.status == HealthStatus.HEALTHY),
            }
        )

    async def check_dependency(self, dependency_name: str) -> DependencyHealth:
        """Check health of a specific dependency."""
        if dependency_name not in self.dependencies:
            return DependencyHealth(
                name=dependency_name,
                status=HealthStatus.UNKNOWN,
                message=f"Dependency '{dependency_name}' not found"
            )

        checker = self.dependencies[dependency_name]
        return await self._check_dependency_safe(dependency_name, checker)

    async def _check_dependency_safe(self, name: str, checker: IHealthCheck) -> DependencyHealth:
        """Check dependency with error handling."""
        start_time = time.time()
        try:
            result = await asyncio.wait_for(
                checker.check_readiness(),
                timeout=5.0  # 5 second timeout for health checks
            )

            response_time_ms = (time.time() - start_time) * 1000

            return DependencyHealth(
                name=name,
                status=result.status,
                message=result.message,
                last_check=result.timestamp,
                response_time_ms=response_time_ms,
                metadata=result.metadata
            )

        except asyncio.TimeoutError:
            return DependencyHealth(
                name=name,
                status=HealthStatus.UNHEALTHY,
                message=f"Health check timed out after 5 seconds",
                last_check=datetime.utcnow()
            )
        except Exception as e:
            return DependencyHealth(
                name=name,
                status=HealthStatus.UNHEALTHY,
                message=f"Health check failed: {str(e)}",
                last_check=datetime.utcnow()
            )

    def _generate_readiness_message(
        self,
        status: HealthStatus,
        dependencies: List[DependencyHealth]
    ) -> str:
        """Generate readiness message based on status and dependencies."""
        if status == HealthStatus.HEALTHY:
            return f"{self.app_name} is ready"

        unhealthy = [d.name for d in dependencies if d.status == HealthStatus.UNHEALTHY]
        degraded = [d.name for d in dependencies if d.status == HealthStatus.DEGRADED]

        if unhealthy:
            return f"{self.app_name} is not ready. Unhealthy dependencies: {', '.join(unhealthy)}"
        elif degraded:
            return f"{self.app_name} is degraded. Degraded dependencies: {', '.join(degraded)}"

        return f"{self.app_name} status: {status.value}"

    def register_dependency(self, name: str, checker: IHealthCheck) -> None:
        """Register a new dependency health check."""
        self.dependencies[name] = checker

    def unregister_dependency(self, name: str) -> None:
        """Unregister a dependency health check."""
        self.dependencies.pop(name, None)


class CompositeHealthCheck(IHealthCheck):
    """
    Composite health check that aggregates multiple checks.

    Useful for grouping related health checks.
    """

    def __init__(self, checks: Optional[List[IHealthCheck]] = None):
        """
        Initialize composite health check.

        Args:
            checks: List of health checks to aggregate
        """
        self.checks = checks or []

    async def check_liveness(self) -> HealthCheckResult:
        """Check liveness of all sub-checks."""
        results = await asyncio.gather(*[check.check_liveness() for check in self.checks])

        # All must be healthy for liveness
        overall_status = HealthStatus.HEALTHY
        for result in results:
            if result.status != HealthStatus.HEALTHY:
                overall_status = HealthStatus.UNHEALTHY
                break

        return HealthCheckResult(
            status=overall_status,
            message=f"Composite liveness check: {overall_status.value}"
        )

    async def check_readiness(self) -> HealthCheckResult:
        """Check readiness of all sub-checks."""
        results = await asyncio.gather(*[check.check_readiness() for check in self.checks])

        # Determine overall status
        overall_status = HealthStatus.HEALTHY
        for result in results:
            if result.status == HealthStatus.UNHEALTHY:
                overall_status = HealthStatus.UNHEALTHY
                break
            elif result.status == HealthStatus.DEGRADED:
                overall_status = HealthStatus.DEGRADED

        return HealthCheckResult(
            status=overall_status,
            message=f"Composite readiness check: {overall_status.value}"
        )

    async def check_dependency(self, dependency_name: str) -> DependencyHealth:
        """Not applicable for composite checks."""
        return DependencyHealth(
            name=dependency_name,
            status=HealthStatus.UNKNOWN,
            message="Composite health check does not support individual dependency checks"
        )


class DatabaseHealthCheck(IHealthCheck):
    """Health check for database connections."""

    def __init__(self, check_func: Callable[[], bool], db_name: str = "database"):
        """
        Initialize database health check.

        Args:
            check_func: Async function that returns True if database is healthy
            db_name: Name of the database
        """
        self.check_func = check_func
        self.db_name = db_name

    async def check_liveness(self) -> HealthCheckResult:
        """Liveness doesn't depend on database."""
        return HealthCheckResult(
            status=HealthStatus.HEALTHY,
            message=f"{self.db_name} health check is alive"
        )

    async def check_readiness(self) -> HealthCheckResult:
        """Check if database is reachable."""
        start_time = time.time()
        try:
            is_healthy = await self.check_func()
            response_time = (time.time() - start_time) * 1000

            if is_healthy:
                return HealthCheckResult(
                    status=HealthStatus.HEALTHY,
                    message=f"{self.db_name} is reachable",
                    metadata={"response_time_ms": response_time}
                )
            else:
                return HealthCheckResult(
                    status=HealthStatus.UNHEALTHY,
                    message=f"{self.db_name} is not healthy"
                )

        except Exception as e:
            return HealthCheckResult(
                status=HealthStatus.UNHEALTHY,
                message=f"{self.db_name} check failed: {str(e)}"
            )

    async def check_dependency(self, dependency_name: str) -> DependencyHealth:
        """Check database health."""
        result = await self.check_readiness()
        return DependencyHealth(
            name=self.db_name,
            status=result.status,
            message=result.message,
            last_check=result.timestamp
        )


class RedisHealthCheck(IHealthCheck):
    """Health check for Redis connections."""

    def __init__(self, check_func: Callable[[], bool], redis_name: str = "redis"):
        """
        Initialize Redis health check.

        Args:
            check_func: Async function that returns True if Redis is healthy
            redis_name: Name of the Redis instance
        """
        self.check_func = check_func
        self.redis_name = redis_name

    async def check_liveness(self) -> HealthCheckResult:
        """Liveness doesn't depend on Redis."""
        return HealthCheckResult(
            status=HealthStatus.HEALTHY,
            message=f"{self.redis_name} health check is alive"
        )

    async def check_readiness(self) -> HealthCheckResult:
        """Check if Redis is reachable."""
        start_time = time.time()
        try:
            is_healthy = await self.check_func()
            response_time = (time.time() - start_time) * 1000

            if is_healthy:
                return HealthCheckResult(
                    status=HealthStatus.HEALTHY,
                    message=f"{self.redis_name} is reachable",
                    metadata={"response_time_ms": response_time}
                )
            else:
                return HealthCheckResult(
                    status=HealthStatus.UNHEALTHY,
                    message=f"{self.redis_name} is not healthy"
                )

        except Exception as e:
            return HealthCheckResult(
                status=HealthStatus.UNHEALTHY,
                message=f"{self.redis_name} check failed: {str(e)}"
            )

    async def check_dependency(self, dependency_name: str) -> DependencyHealth:
        """Check Redis health."""
        result = await self.check_readiness()
        return DependencyHealth(
            name=self.redis_name,
            status=result.status,
            message=result.message,
            last_check=result.timestamp
        )


class EventStoreHealthCheck(IHealthCheck):
    """Health check for event store."""

    def __init__(self, check_func: Callable[[], bool], store_name: str = "event_store"):
        """
        Initialize event store health check.

        Args:
            check_func: Async function that returns True if event store is healthy
            store_name: Name of the event store
        """
        self.check_func = check_func
        self.store_name = store_name

    async def check_liveness(self) -> HealthCheckResult:
        """Liveness doesn't depend on event store."""
        return HealthCheckResult(
            status=HealthStatus.HEALTHY,
            message=f"{self.store_name} health check is alive"
        )

    async def check_readiness(self) -> HealthCheckResult:
        """Check if event store is reachable."""
        start_time = time.time()
        try:
            is_healthy = await self.check_func()
            response_time = (time.time() - start_time) * 1000

            if is_healthy:
                return HealthCheckResult(
                    status=HealthStatus.HEALTHY,
                    message=f"{self.store_name} is reachable",
                    metadata={"response_time_ms": response_time}
                )
            else:
                return HealthCheckResult(
                    status=HealthStatus.UNHEALTHY,
                    message=f"{self.store_name} is not healthy"
                )

        except Exception as e:
            return HealthCheckResult(
                status=HealthStatus.UNHEALTHY,
                message=f"{self.store_name} check failed: {str(e)}"
            )

    async def check_dependency(self, dependency_name: str) -> DependencyHealth:
        """Check event store health."""
        result = await self.check_readiness()
        return DependencyHealth(
            name=self.store_name,
            status=result.status,
            message=result.message,
            last_check=result.timestamp
        )


class CircuitBreakerHealthCheck(IHealthCheck):
    """Health check for circuit breaker state."""

    def __init__(self, circuit_breaker: ICircuitBreaker, name: str = "circuit_breaker"):
        """
        Initialize circuit breaker health check.

        Args:
            circuit_breaker: Circuit breaker to monitor
            name: Name for the circuit breaker
        """
        self.circuit_breaker = circuit_breaker
        self.name = name

    async def check_liveness(self) -> HealthCheckResult:
        """Liveness doesn't depend on circuit breaker."""
        return HealthCheckResult(
            status=HealthStatus.HEALTHY,
            message=f"{self.name} health check is alive"
        )

    async def check_readiness(self) -> HealthCheckResult:
        """Check circuit breaker state."""
        state = self.circuit_breaker.get_state()
        stats = self.circuit_breaker.get_stats()

        if state == CircuitState.CLOSED:
            status = HealthStatus.HEALTHY
            message = f"{self.name} is closed (healthy)"
        elif state == CircuitState.HALF_OPEN:
            status = HealthStatus.DEGRADED
            message = f"{self.name} is half-open (testing recovery)"
        else:  # OPEN
            status = HealthStatus.UNHEALTHY
            message = f"{self.name} is open (failing)"

        return HealthCheckResult(
            status=status,
            message=message,
            metadata={
                "state": state.value,
                "failure_count": stats.failure_count,
                "success_count": stats.success_count,
                "total_calls": stats.total_calls,
            }
        )

    async def check_dependency(self, dependency_name: str) -> DependencyHealth:
        """Check circuit breaker health."""
        result = await self.check_readiness()
        return DependencyHealth(
            name=self.name,
            status=result.status,
            message=result.message,
            last_check=result.timestamp,
            metadata=result.metadata
        )


class RateLimiterHealthCheck(IHealthCheck):
    """Health check for rate limiter state."""

    def __init__(self, rate_limiter: IRateLimiter, name: str = "rate_limiter", warn_threshold: float = 0.8):
        """
        Initialize rate limiter health check.

        Args:
            rate_limiter: Rate limiter to monitor
            name: Name for the rate limiter
            warn_threshold: Utilization threshold for degraded status (0.0-1.0)
        """
        self.rate_limiter = rate_limiter
        self.name = name
        self.warn_threshold = warn_threshold

    async def check_liveness(self) -> HealthCheckResult:
        """Liveness doesn't depend on rate limiter."""
        return HealthCheckResult(
            status=HealthStatus.HEALTHY,
            message=f"{self.name} health check is alive"
        )

    async def check_readiness(self) -> HealthCheckResult:
        """Check rate limiter utilization."""
        stats = self.rate_limiter.get_stats()

        if stats.utilization >= 1.0:
            status = HealthStatus.UNHEALTHY
            message = f"{self.name} is at capacity (100% utilization)"
        elif stats.utilization >= self.warn_threshold:
            status = HealthStatus.DEGRADED
            message = f"{self.name} is under high load ({stats.utilization*100:.1f}% utilization)"
        else:
            status = HealthStatus.HEALTHY
            message = f"{self.name} is healthy ({stats.utilization*100:.1f}% utilization)"

        return HealthCheckResult(
            status=status,
            message=message,
            metadata={
                "utilization": stats.utilization,
                "requests_in_window": stats.requests_in_window,
                "max_requests": stats.max_requests,
                "window_seconds": stats.window_seconds,
            }
        )

    async def check_dependency(self, dependency_name: str) -> DependencyHealth:
        """Check rate limiter health."""
        result = await self.check_readiness()
        return DependencyHealth(
            name=self.name,
            status=result.status,
            message=result.message,
            last_check=result.timestamp,
            metadata=result.metadata
        )
