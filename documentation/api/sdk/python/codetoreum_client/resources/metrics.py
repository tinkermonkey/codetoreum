"""Metrics resource client"""

from typing import Any, TYPE_CHECKING

if TYPE_CHECKING:
    from ..client import CodetoreumClient


class MetricsResource:
    """Client for metrics endpoints."""

    def __init__(self, client: "CodetoreumClient") -> None:
        self.client = client

    def health(self) -> dict[str, Any]:
        """Get system health check."""
        return self.client.get("/api/v2/metrics/health")

    def performance(self) -> dict[str, Any]:
        """Get performance metrics."""
        return self.client.get("/api/v2/metrics/performance")

    def resilience(self) -> dict[str, Any]:
        """Get resilience infrastructure metrics."""
        return self.client.get("/api/v2/metrics/resilience")

    def integration_status(self) -> dict[str, Any]:
        """Get integration status."""
        return self.client.get("/api/v2/metrics/integration-status")
