"""Workspaces resource client"""


class WorkspacesResource:
    """Client for workspaces endpoints."""

    def __init__(self, client):
        self.client = client

    def list(self) -> list:
        """List all workspaces."""
        data = self.client.get("/api/v2/workspace/status")
        return data.get("workspaces", [])

    def get(self, workspace_id: str) -> dict:
        """Get workspace status."""
        return self.client.get(f"/api/v2/workspace/{workspace_id}")

    def get_resource_usage(self) -> dict:
        """Get resource usage summary."""
        return self.client.get("/api/v2/workspace/resource-usage")
