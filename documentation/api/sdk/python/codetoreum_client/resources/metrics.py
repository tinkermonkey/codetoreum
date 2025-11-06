"""Metrics resource client"""


class MetricsResource:
    """Client for metrics endpoints."""

    def __init__(self, client):
        self.client = client

    def health(self) -> dict:
        """Get system health check."""
        return self.client.get("/api/v2/metrics/health")

    def performance(self) -> dict:
        """Get performance metrics."""
        return self.client.get("/api/v2/metrics/performance")

    def resilience(self) -> dict:
        """Get resilience infrastructure metrics."""
        return self.client.get("/api/v2/metrics/resilience")

    def integration_status(self) -> dict:
        """Get integration status."""
        return self.client.get("/api/v2/metrics/integration-status")
