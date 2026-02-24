"""Metrics resource client"""

from typing import Any, Dict


class MetricsResource:
    """Client for metrics endpoints."""

    def __init__(self, client: Any) -> None:
        self.client = client

    def health(self) -> Dict[Any, Any]:
        """Get system health check."""
        return self.client.get("/api/v2/metrics/health")

    def performance(self) -> Dict[Any, Any]:
        """Get performance metrics."""
        return self.client.get("/api/v2/metrics/performance")

    def resilience(self) -> Dict[Any, Any]:
        """Get resilience infrastructure metrics."""
        return self.client.get("/api/v2/metrics/resilience")

    def integration_status(self) -> Dict[Any, Any]:
        """Get integration status."""
        return self.client.get("/api/v2/metrics/integration-status")
