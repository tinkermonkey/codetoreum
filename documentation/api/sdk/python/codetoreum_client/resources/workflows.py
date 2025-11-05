"""Workflows resource client"""
from ..models import Workflow, PaginatedResponse


class WorkflowsResource:
    """Client for workflows endpoints."""

    def __init__(self, client):
        self.client = client

    def create(self, name: str, description: str, stages: list, **kwargs) -> Workflow:
        """Create a workflow definition."""
        payload = {"name": name, "description": description, "stages": stages, **kwargs}
        data = self.client.post("/api/v2/workflows/", json=payload)
        return Workflow.from_dict(data)

    def list(self, **filters) -> PaginatedResponse:
        """List workflows."""
        data = self.client.get("/api/v2/workflows/", params=filters)
        return PaginatedResponse.from_dict(data, Workflow)

    def get(self, workflow_id: str) -> Workflow:
        """Get workflow definition."""
        data = self.client.get(f"/api/v2/workflows/{workflow_id}")
        return Workflow.from_dict(data)

    def update(self, workflow_id: str, **updates) -> Workflow:
        """Update workflow definition."""
        data = self.client.put(f"/api/v2/workflows/{workflow_id}", json=updates)
        return Workflow.from_dict(data)

    def delete(self, workflow_id: str) -> dict:
        """Delete workflow definition."""
        return self.client.delete(f"/api/v2/workflows/{workflow_id}")
