"""Health check interfaces.

Defines contracts for liveness and readiness probes.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Dict, List, Optional


class HealthStatus(Enum):
    """Health status enumeration."""
    HEALTHY = "healthy"
    UNHEALTHY = "unhealthy"
    DEGRADED = "degraded"
    UNKNOWN = "unknown"


@dataclass
class DependencyHealth:
    """Health status of a dependency."""
    name: str
    status: HealthStatus
    message: Optional[str] = None
    last_check: Optional[datetime] = None
    response_time_ms: Optional[float] = None
    metadata: Optional[Dict] = None


@dataclass
class HealthCheckResult:
    """Result of a health check."""
    status: HealthStatus
    message: Optional[str] = None
    timestamp: Optional[datetime] = None
    dependencies: List[DependencyHealth] = field(default_factory=list)
    metadata: Dict = field(default_factory=dict)

    def __post_init__(self):
        if self.timestamp is None:
            self.timestamp = datetime.now(timezone.utc)


class IHealthCheck(ABC):
    """
    Health check interface.

    Provides methods for checking system health, readiness, and liveness.
    """

    @abstractmethod
    async def check_liveness(self) -> HealthCheckResult:
        """
        Check if the application is alive.

        Liveness checks verify that the application is running and not deadlocked.
        Should be fast and not depend on external services.

        Returns:
            HealthCheckResult indicating if the application is alive
        """
        pass

    @abstractmethod
    async def check_readiness(self) -> HealthCheckResult:
        """
        Check if the application is ready to serve requests.

        Readiness checks verify that the application and its dependencies
        are healthy and can handle requests.

        Returns:
            HealthCheckResult indicating if the application is ready
        """
        pass

    @abstractmethod
    async def check_dependency(self, dependency_name: str) -> DependencyHealth:
        """
        Check health of a specific dependency.

        Args:
            dependency_name: Name of the dependency to check

        Returns:
            DependencyHealth for the specified dependency
        """
        pass
