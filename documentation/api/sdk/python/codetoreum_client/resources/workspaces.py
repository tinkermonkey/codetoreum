"""Workspaces resource client"""

from typing import Any


class WorkspacesResource:
    """Client for workspaces endpoints."""

    def __init__(self, client: Any) -> None:
        self.client = client

    def list(self) -> list[Any]:
        """List all workspaces."""
        data: dict[str, Any] = self.client.get("/api/v2/workspace/status")
        result: list[Any] = data.get("workspaces", [])
        return result

    def get(self, workspace_id: str) -> dict[str, Any]:
        """Get workspace status."""
        result: dict[str, Any] = self.client.get(f"/api/v2/workspace/{workspace_id}")
        return result

    def get_resource_usage(self) -> dict[str, Any]:
        """Get resource usage summary."""
        result: dict[str, Any] = self.client.get("/api/v2/workspace/resource-usage")
        return result
